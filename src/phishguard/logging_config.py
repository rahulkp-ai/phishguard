"""
phishguard.logging_config
==========================
Configures structlog and the stdlib logging root handler.

Call ``configure_logging(env)`` once at application startup (in the Flask
app factory or the training pipeline entry point).  Every other module
just does::

    import structlog
    logger = structlog.get_logger(__name__)

Design decisions
----------------
- **structlog** is the front-end for all logging in this project.  It adds
  key=value context to every log line automatically and lets us attach
  per-request context (request_id, url, latency) without passing arguments
  through every call stack.
- **stdlib logging** is still configured as the back-end because third-party
  libraries (Flask, sklearn, gunicorn) log through it.  structlog's
  ``stdlib.ProcessorFormatter`` bridges the two so all output is uniform.
- **Development** output: coloured, human-readable (ConsoleRenderer).
- **Production** output: JSON per line — machine-parseable, works with
  Datadog / CloudWatch / Loki / any log aggregator.
- **Test** output: minimal — only WARNING and above to avoid noise in
  pytest output.

Output examples
---------------
Development::

    2024-01-15 14:32:01 [info     ] request started   [phishguard] method=POST path=/api/predict request_id=a1b2c3d4

Production (JSON)::

    {"timestamp": "2024-01-15T14:32:01.123Z", "level": "info", "event": "prediction complete",
     "logger": "phishguard.app.routes", "request_id": "a1b2c3d4", "url": "https://example.com",
     "is_phishing": false, "confidence": 92.4, "latency_ms": 8.3}
"""

from __future__ import annotations

import logging
import logging.config
import sys
from typing import Literal

import structlog

Env = Literal["development", "production", "testing"]

# Processors that run on every log record regardless of environment.
# They add timestamps, log level, and the logger name to every event.
_SHARED_PROCESSORS: list = [
    structlog.contextvars.merge_contextvars,  # merges request_id etc.
    structlog.stdlib.add_logger_name,  # adds "logger" key
    structlog.stdlib.add_log_level,  # adds "level" key
    structlog.stdlib.PositionalArgumentsFormatter(),  # handles %s-style args
    structlog.processors.TimeStamper(fmt="iso"),  # ISO-8601 timestamp
    structlog.processors.StackInfoRenderer(),
]


def configure_logging(env: Env = "development", level: str = "INFO") -> None:
    """
    Configure structlog and stdlib logging for *env*.

    Call this once at startup — in the Flask app factory or the training
    script's entry point.

    Parameters
    ----------
    env:
        ``"development"`` → coloured console output
        ``"production"``  → JSON per line
        ``"testing"``     → WARNING+ only, plain text
    level:
        Minimum log level string (``"DEBUG"``, ``"INFO"``, ``"WARNING"``…).
        Overridden to ``"WARNING"`` when *env* is ``"testing"``.
    """
    if env == "testing":
        level = "WARNING"

    # ------------------------------------------------------------------
    # stdlib logging configuration
    # ------------------------------------------------------------------
    # structlog's ProcessorFormatter is installed as a stdlib Formatter so
    # that third-party libraries (Flask, werkzeug, sklearn) have their log
    # records rendered through the same pipeline.
    # ------------------------------------------------------------------
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        # Extract the log record from the event dict so
                        # structlog can render stdlib records too.
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        _get_renderer(env),
                    ],
                    "foreign_pre_chain": _SHARED_PROCESSORS,
                },
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "handlers": ["console"],
                "level": level,
            },
            # Quieten noisy third-party loggers in development
            "loggers": {
                "werkzeug": {"level": "WARNING" if env != "development" else "INFO"},
                "urllib3": {"level": "WARNING"},
                "requests": {"level": "WARNING"},
            },
        }
    )

    # ------------------------------------------------------------------
    # structlog configuration
    # ------------------------------------------------------------------
    structlog.configure(
        processors=_SHARED_PROCESSORS
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def _get_renderer(env: Env):
    """Return the final structlog renderer for *env*."""
    if env == "production":
        return structlog.processors.JSONRenderer()
    # development and testing
    return structlog.dev.ConsoleRenderer(colors=(env == "development" and sys.stdout.isatty()))
