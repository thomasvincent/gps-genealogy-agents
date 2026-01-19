"""Structlog-based logging for GPS Genealogy Agents.

Complies with hard rule: use structlog; no print() in library code.
"""
from __future__ import annotations

from typing import Literal

import logging
import structlog

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


def configure_logging(level: LogLevel = "INFO") -> None:
    logging.basicConfig(format="%(message)s", level=getattr(logging, level))
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "gps_agents"):
    return structlog.get_logger(name)


# Initialize default config
configure_logging()
