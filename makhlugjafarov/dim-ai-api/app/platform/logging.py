import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.platform.observability.correlation import RequestIdFilter

AUTHORIZATION_PATTERN = re.compile(r"(?i)\b(authorization)(\s*[=:]\s*)(bearer\s+)?([^\s,;]+)")
SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|bearer|jwt|password|secret|service[_-]?role[_-]?key|token)"
    r"(\s*[=:]\s*|\s+)"
    r"([^\s,;]+)"
)


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        redacted = AUTHORIZATION_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
        return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", redacted)
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _looks_secret_key(str(key)) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def _looks_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in ("api_key", "authorization", "jwt", "password", "secret", "token"))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add request_id if injected by RequestIdFilter
        if hasattr(record, "request_id") and record.request_id:
            payload["request_id"] = record.request_id

        # Merge in any extra dicts passed to logger.info(extra={...})
        for key, value in record.__dict__.items():
            if key not in {"args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process", "processName", "relativeCreated", "stack_info", "thread", "threadName", "taskName", "request_id"}:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(redact_secrets(payload), ensure_ascii=False)


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if isinstance(record.args, tuple) and record.args:
            record.args = tuple(redact_secrets(arg) for arg in record.args)
        elif isinstance(record.args, dict):
            record.args = redact_secrets(record.args)
        return True


def configure_logging(level: str = "INFO", dim_debug: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level.upper())

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    # Always apply redaction. Never bypassable.
    handler.addFilter(SecretRedactionFilter())
    handler.addFilter(RequestIdFilter())
    root.addHandler(handler)

    if dim_debug:
        logging.getLogger("dim").setLevel(logging.DEBUG)
        logging.getLogger("httpx").setLevel(logging.INFO)  # keep third parties quiet unless explicitly raised
