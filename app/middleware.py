"""
app.middleware
==============
WSGI middleware and Flask hooks that add per-request observability.

What this module provides
--------------------------
``RequestIdMiddleware``
    Wraps the WSGI app.  Reads ``X-Request-ID`` from the incoming request
    header (so load balancers / API gateways can set their own IDs), or
    generates a new UUID if the header is absent.  The ID is:
    - Stored in Flask's ``g`` object (``g.request_id``).
    - Injected into structlog's context so every log line during the
      request automatically includes ``request_id=...``.
    - Echoed back in the ``X-Request-ID`` response header.

``register_request_logging``
    Attaches ``before_request`` / ``after_request`` / ``teardown_request``
    hooks to the Flask app that log:
    - Request start: method, path, remote IP.
    - Request end: status code, latency in ms.
    - Any unhandled exceptions (with stack trace via ``exc_info``).

Why structlog.contextvars?
--------------------------
structlog's ``contextvars`` module stores context in Python's
``contextvars.ContextVar``, which is per-coroutine in async code and
effectively per-request in synchronous WSGI (each request runs in its own
thread / greenlet).  This means we call ``bind_contextvars(request_id=...)``
once at request start and every subsequent log call in that request thread
automatically includes it — no thread-local gymnastics, no argument passing.
"""

from __future__ import annotations

import time
import uuid

import structlog
from flask import Flask, g, request

logger = structlog.get_logger(__name__)


def register_request_logging(app: Flask) -> None:
    """
    Attach request lifecycle hooks to *app*.

    Call this inside ``create_app()`` after the blueprints are registered.
    """

    @app.before_request
    def _before() -> None:
        # Generate or inherit a request ID
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        g.request_id = request_id
        g.request_start = time.perf_counter()

        # Bind into structlog context — every log line in this request
        # will automatically include request_id=..., method=..., path=...
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.path,
        )

        logger.info("request started", remote_addr=request.remote_addr)

    @app.after_request
    def _after(response):
        latency_ms = round((time.perf_counter() - g.get("request_start", time.perf_counter())) * 1000, 2)
        status = response.status_code

        # Echo the request ID back so callers can correlate client + server logs
        response.headers["X-Request-ID"] = g.get("request_id", "unknown")

        log_fn = logger.warning if status >= 400 else logger.info
        log_fn(
            "request complete",
            status=status,
            latency_ms=latency_ms,
        )
        return response

    @app.teardown_request
    def _teardown(exc) -> None:
        if exc is not None:
            logger.error(
                "unhandled exception",
                exc_info=exc,
            )
        # Always clear structlog context at the end of the request
        structlog.contextvars.clear_contextvars()
