"""Logging configuration for GPS Genealogy Agents.

Provides consistent logging across all modules with configurable levels.
"""

from __future__ import annotations

import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Module-level logger
_logger: logging.Logger | None = None


def get_logger(name: str = "gps_agents") -> logging.Logger:
    """Get a logger instance for the given module name.

    Args:
        name: Logger name (usually __name__ of the calling module)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def configure_logging(
    level: LogLevel = "INFO",
    format_string: str | None = None,
) -> logging.Logger:
    """Configure the root GPS agents logger.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_string: Custom format string (optional)

    Returns:
        The configured root logger
    """
    global _logger

    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # Configure root logger for gps_agents
    logger = logging.getLogger("gps_agents")
    logger.setLevel(getattr(logging, level))

    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()

    # Add console handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(getattr(logging, level))
    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    _logger = logger
    return logger


# Configure on import with default settings
configure_logging()
