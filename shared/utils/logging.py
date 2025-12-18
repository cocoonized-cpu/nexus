"""
Logging configuration for NEXUS services.
"""

import logging
import sys
from typing import Optional

import structlog


def setup_logging(
    service_name: str,
    level: str = "INFO",
    json_format: bool = True,
) -> None:
    """
    Configure structured logging for a service.

    Args:
        service_name: Name of the service for log context
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        json_format: Whether to output JSON (True) or human-readable (False)
    """
    # Set up standard logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )

    # Configure structlog
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        processors.extend(
            [
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ]
        )
    else:
        processors.extend(
            [
                structlog.dev.ConsoleRenderer(colors=True),
            ]
        )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bind service name to all logs
    structlog.contextvars.bind_contextvars(service=service_name)


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    Get a logger instance.

    Args:
        name: Optional logger name for context

    Returns:
        Configured logger instance
    """
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(module=name)
    return logger


class LoggerMixin:
    """Mixin class to add logging to any class."""

    @property
    def logger(self) -> structlog.BoundLogger:
        """Get logger bound to this class."""
        if not hasattr(self, "_logger"):
            self._logger = get_logger(self.__class__.__name__)
        return self._logger
