"""Prodinamik Engine v1.0 — Logging

Standard logging module with structured output support.
"""

import logging
import sys
from typing import Optional
from .config import LoggingConfig


# Module-level logger
_logger: Optional[logging.Logger] = None


class StructuredFormatter(logging.Formatter):
    """Simple JSON-like structured formatter for machine parsing"""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "name": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0]:
            log["exc"] = self.formatException(record.exc_info)
        import json
        return json.dumps(log, ensure_ascii=False)


def setup(config: Optional[LoggingConfig] = None) -> logging.Logger:
    """Configure and return the root logger"""
    global _logger

    cfg = config or LoggingConfig()

    level = getattr(logging, cfg.level.upper(), logging.INFO)

    logger = logging.getLogger("prodinamik")
    logger.setLevel(level)
    logger.handlers.clear()

    if cfg.format == "json":
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if cfg.file:
        file_handler = logging.FileHandler(cfg.file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    """Get the configured logger, or a default one if not yet setup"""
    global _logger
    if _logger is None:
        _logger = setup()
    return _logger


# Convenience
def debug(msg: str, *args, **kwargs):
    get_logger().debug(msg, *args, **kwargs)


def info(msg: str, *args, **kwargs):
    get_logger().info(msg, *args, **kwargs)


def warn(msg: str, *args, **kwargs):
    get_logger().warning(msg, *args, **kwargs)


def error(msg: str, *args, **kwargs):
    get_logger().error(msg, *args, **kwargs)
