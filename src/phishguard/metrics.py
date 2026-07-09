"""
phishguard.metrics
==================
Central registry of all Prometheus metrics for PhishGuard.

Design decisions
----------------
All metrics are defined here in one module and imported wherever they are
needed.  This approach has three benefits:

1. **No duplicate registration errors.**  Prometheus raises a ValueError if
   you register two metrics with the same name.  With metrics scattered
   across modules, this is easy to trigger — especially in tests that
   create multiple Flask app instances.  Centralising here means each metric
   is registered exactly once at import time.

2. **Single source of truth for metric names and labels.**  Metric names
   follow the Prometheus naming convention:
   ``<namespace>_<subsystem>_<unit>``.
   All PhishGuard metrics use the ``phishguard`` namespace.

3. **Easy to mock in tests.**  Tests import from this module directly
   rather than having to patch multiple locations.

Metric naming convention used here
------------------------------------
phishguard_http_requests_total          — counter (labelled by method, endpoint, status)
phishguard_http_request_duration_seconds — histogram (latency per endpoint)
phishguard_predictions_total            — counter (labelled by label, risk_level)
phishguard_prediction_confidence        — histogram (confidence score distribution)
phishguard_batch_size                   — histogram (URLs per batch request)
phishguard_model_load_duration_seconds  — histogram (time to load model from disk)
phishguard_active_requests              — gauge (in-flight requests right now)
phishguard_phishing_rate_1m             — gauge (rolling 1-min phishing prediction %)
phishguard_drift_detected               — gauge (0/1 — is drift currently active?)
phishguard_feature_extraction_seconds  — histogram (feature extraction latency)
"""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram
from prometheus_client import CollectorRegistry

# ---------------------------------------------------------------------------
# Use the default registry.
# In tests we create a separate registry per test to avoid cross-test
# pollution — see tests/test_metrics.py.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HTTP request metrics
# ---------------------------------------------------------------------------

HTTP_REQUESTS_TOTAL = Counter(
    name="phishguard_http_requests_total",
    documentation="Total HTTP requests received, labelled by method, endpoint, and HTTP status.",
    labelnames=["method", "endpoint", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    name="phishguard_http_request_duration_seconds",
    documentation="HTTP request latency in seconds, labelled by method and endpoint.",
    labelnames=["method", "endpoint"],
    # Buckets tuned for an ML inference API:
    # Most requests: 5–50 ms. Batch requests: up to 2s.
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

ACTIVE_REQUESTS = Gauge(
    name="phishguard_active_requests",
    documentation="Number of HTTP requests currently being processed.",
)

# ---------------------------------------------------------------------------
# Prediction metrics
# ---------------------------------------------------------------------------

PREDICTIONS_TOTAL = Counter(
    name="phishguard_predictions_total",
    documentation="Total URL predictions made, labelled by classification label and risk level.",
    labelnames=["label", "risk_level"],
)

PREDICTION_CONFIDENCE = Histogram(
    name="phishguard_prediction_confidence",
    documentation="Distribution of model confidence scores (0–100).",
    buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 99, 100],
)

BATCH_SIZE = Histogram(
    name="phishguard_batch_size",
    documentation="Number of URLs per batch prediction request.",
    buckets=[1, 2, 5, 10, 20, 30, 50],
)

FEATURE_EXTRACTION_DURATION = Histogram(
    name="phishguard_feature_extraction_seconds",
    documentation="Time taken to extract features from a single URL.",
    buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1],
)

# ---------------------------------------------------------------------------
# Model metrics
# ---------------------------------------------------------------------------

MODEL_LOAD_DURATION = Histogram(
    name="phishguard_model_load_duration_seconds",
    documentation="Time taken to load the model from disk on startup.",
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
)

MODEL_LOADED = Gauge(
    name="phishguard_model_loaded",
    documentation="1 if the model is currently loaded in memory, 0 otherwise.",
)

# ---------------------------------------------------------------------------
# Drift detection metrics
# ---------------------------------------------------------------------------

PHISHING_RATE = Gauge(
    name="phishguard_phishing_rate_1m",
    documentation=(
        "Rolling 1-minute phishing prediction rate (0.0–1.0). "
        "Computed over the last 60 predictions."
    ),
)

DRIFT_DETECTED = Gauge(
    name="phishguard_drift_detected",
    documentation=(
        "1 if prediction drift is currently detected (phishing rate has "
        "deviated significantly from baseline), 0 otherwise."
    ),
)

DRIFT_BASELINE = Gauge(
    name="phishguard_drift_baseline",
    documentation="Configured baseline phishing rate used for drift detection.",
)
