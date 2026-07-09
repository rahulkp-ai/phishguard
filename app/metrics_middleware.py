"""
app.metrics_middleware
======================
Instruments every Flask HTTP request with Prometheus metrics automatically.

This middleware uses the same Flask lifecycle hooks pattern as
``app/middleware.py`` (request logging).  The two are separate modules
so each has a single clear responsibility.

What gets instrumented
-----------------------
Every request (regardless of endpoint) automatically records:
- ``phishguard_http_requests_total``       [method, endpoint, status]
- ``phishguard_http_request_duration_seconds`` [method, endpoint]
- ``phishguard_active_requests``            (in-flight gauge)

The ``endpoint`` label uses Flask's ``request.endpoint`` value (the
function name), not the raw URL path.  This prevents label cardinality
explosion from paths with variable segments like ``/user/12345`` —
they all map to the same ``endpoint`` label value ``user_profile``.

Why not use the flask-prometheus-metrics library?
-------------------------------------------------
Several wrapper libraries exist (prometheus-flask-exporter etc.) but they
add a dependency, make assumptions about label cardinality, and can't be
easily customised.  At 40 lines of code, doing it directly gives full
control and nothing to debug.
"""

from __future__ import annotations

import time

from flask import Flask, g, request

from phishguard.metrics import (
    ACTIVE_REQUESTS,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS_TOTAL,
)

# Endpoints to exclude from metrics — scraping /metrics itself would be circular,
# and /static is noise.  Flask prefixes blueprint endpoints with "main.", so we
# match on the suffix rather than the bare function name.
_EXCLUDED_ENDPOINTS = frozenset({"main.metrics", "static"})


def register_metrics_middleware(app: Flask) -> None:
    """
    Attach Prometheus instrumentation hooks to *app*.

    Call this inside ``create_app()`` after blueprints are registered.
    """

    @app.before_request
    def _start_timer() -> None:
        g.metrics_start = time.perf_counter()
        endpoint = request.endpoint or "unknown"
        if endpoint not in _EXCLUDED_ENDPOINTS:
            ACTIVE_REQUESTS.inc()

    @app.after_request
    def _record_metrics(response):
        endpoint = request.endpoint or "unknown"
        if endpoint in _EXCLUDED_ENDPOINTS:
            return response

        ACTIVE_REQUESTS.dec()

        duration = time.perf_counter() - g.get("metrics_start", time.perf_counter())
        method = request.method
        status = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=method,
            endpoint=endpoint,
            status=status,
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)

        return response
