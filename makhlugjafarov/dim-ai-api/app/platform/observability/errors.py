"""Error taxonomy and structured logging helpers."""

import logging
from typing import Any

from app.platform.observability.correlation import request_id_ctx

logger = logging.getLogger("dim.errors")

def log_domain_error(exc: Exception, code: str, context: dict[str, Any] | None = None) -> None:
    """
    Logs a domain error at the boundary, ensuring a stable code and correlation ID.
    Redaction is handled automatically by the global logging filter.
    """
    payload = {
        "error_code": code,
        "error_type": exc.__class__.__name__,
        "error_message": str(exc),
        "request_id": request_id_ctx.get(),
    }
    if context:
        payload["context"] = context

    logger.error(f"Domain Error [{code}]: {str(exc)}", extra={"error_details": payload}, exc_info=exc)
