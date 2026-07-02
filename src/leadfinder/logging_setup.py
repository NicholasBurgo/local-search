"""Structured logging for leadfinder (file + console), ASCII output."""

from __future__ import annotations

import logging
import os
from datetime import datetime

LOGGER_NAME = "leadfinder"

_VALID_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """Configure and return the shared 'leadfinder' logger.

    Writes to a timestamped file under log_dir and to the console. Idempotent:
    re-calling clears prior handlers so tests and repeat runs do not duplicate output.

    Raises:
        ValueError: if log_level is not a recognized logging level.
    """
    level = log_level.upper()
    if level not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log_level '{log_level}'. Must be one of: {', '.join(sorted(_VALID_LEVELS))}"
        )

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.propagate = False

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"leadfinder_{timestamp}.log")

    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.setLevel(getattr(logging, level))
    logger.debug("Logging initialized. Log file: %s", log_file)
    return logger


def get_logger() -> logging.Logger:
    """Return the shared logger (without reconfiguring handlers)."""
    return logging.getLogger(LOGGER_NAME)
