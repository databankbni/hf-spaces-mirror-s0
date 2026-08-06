"""
Legacy core logging module.
This module is a backwards-compatibility shim for code that hasn't been migrated
to the new platform observability context.
"""

from app.platform.logging import (
    AUTHORIZATION_PATTERN,
    SECRET_PATTERN,
    JsonFormatter,
    SecretRedactionFilter,
    _looks_secret_key,
    configure_logging,
    redact_secrets,
)

__all__ = [
    "AUTHORIZATION_PATTERN",
    "SECRET_PATTERN",
    "JsonFormatter",
    "SecretRedactionFilter",
    "_looks_secret_key",
    "configure_logging",
    "redact_secrets",
]
