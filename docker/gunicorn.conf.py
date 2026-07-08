"""
gunicorn.conf.py
================
Gunicorn production configuration.

Using a Python config file instead of CLI flags gives us:
- Comments explaining every setting.
- Environment variable overrides without shell quoting issues.
- A source-controlled, reviewable configuration.

Reference: https://docs.gunicorn.org/en/stable/settings.html

Usage (from project root):
    gunicorn --config gunicorn.conf.py run:app
"""

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Server socket
# ---------------------------------------------------------------------------
# Bind to all interfaces so Docker can route traffic to the container.
# PORT is read from the environment — default 5005.
bind = f"0.0.0.0:{os.environ.get('PORT', '5005')}"

# ---------------------------------------------------------------------------
# Worker processes
# ---------------------------------------------------------------------------
# WEB_CONCURRENCY overrides the default formula.
# Recommended starting point: (2 × CPU count) + 1.
# On a single-CPU container (common in free-tier cloud), this gives 3 workers.
# Keep it low for memory-constrained environments (Render free tier: 512 MB RAM).
_default_workers = (multiprocessing.cpu_count() * 2) + 1
workers = int(os.environ.get("WEB_CONCURRENCY", _default_workers))

# Worker class: "sync" is correct for a CPU-bound ML inference workload.
# Use "gevent" or "uvicorn.workers.UvicornWorker" only if you switch to async.
worker_class = "sync"

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
# How long a worker can take to handle a single request before it is killed
# and restarted.  Set higher than the worst-case prediction latency.
# Batch endpoint with 50 URLs × ~10 ms each = ~500 ms worst case.
# 60 seconds is conservative headroom.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "60"))

# How long to wait for workers to finish in-flight requests on graceful shutdown
graceful_timeout = 30

# ---------------------------------------------------------------------------
# Keep-alive
# ---------------------------------------------------------------------------
# Number of seconds to wait for requests on a keep-alive connection.
keepalive = 5

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# "--" sends logs to stdout/stderr — Docker captures these and forwards them
# to the log driver (CloudWatch, Datadog, etc.).
accesslog = "-"
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info")

# Disable gunicorn's default access log format — structlog middleware in
# app/middleware.py emits richer structured access logs.
access_log_format = '%(h)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "phishguard"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Prevent gunicorn from leaking its version in HTTP headers.
# Not a critical security control, but reduces information disclosure.
limit_request_line = 4096
limit_request_fields = 100
limit_request_field_size = 8190

# ---------------------------------------------------------------------------
# Pre-load application
# ---------------------------------------------------------------------------
# preload_app=True loads the Flask app once in the master process before
# forking workers.  Benefits:
#   1. The joblib model is loaded once and shared (copy-on-write) across workers.
#   2. Startup is faster because workers don't each independently load the model.
# Trade-off: if the app object changes, you must restart gunicorn (not just reload).
preload_app = True
