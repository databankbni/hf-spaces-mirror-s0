"""
Logger utility — wraps loguru for structured, coloured console output.
"""
import sys
from loguru import logger as _logger
from config import get_settings


def _configure():
    settings = get_settings()
    _logger.remove()
    _logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        colorize=True,
    )
    _logger.add(
        "storage/codesleuth.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
    )


_configure()


def get_logger(name: str):
    return _logger.bind(name=name)
