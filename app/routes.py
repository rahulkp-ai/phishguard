"""
Flask routes — pages and REST API endpoints.

Phase 8 additions
------------------
- ``/metrics`` endpoint — Prometheus scrape target (text/plain exposition format).
- Prediction metrics recorded after each successful prediction:
  PREDICTIONS_TOTAL, PREDICTION_CONFIDENCE, FEATURE_EXTRACTION_DURATION.
- Batch size recorded on each batch request: BATCH_SIZE.
- Drift detector notified after every prediction.
- Model load time recorded in MODEL_LOAD_DURATION on first load.
- MODEL_LOADED gauge updated when model state changes.
"""

from __future__ import annotations

import time

import joblib
import pandas as pd
import structlog
from flask import Blueprint, current_app, jsonify, render_template, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from phishguard.drift import detector as drift_detector
from phishguard.features.extractor import FEATURE_NAMES, extract_features
from phishguard.metrics import (
    BATCH_SIZE,
    FEATURE_EXTRACTION_DURATION,
    MODEL_LOAD_DURATION,
    MODEL_LOADED,
    PREDICTION_CONFIDENCE,
    PREDICTIONS_TOTAL,
)

main = Blueprint("main", __name__)
logger = structlog.get_logger(__name__)

# Module-level cache — model is loaded once and reused across requests.
_model = None


# ---------------------------------------------------------------------------
# Model loading
# ---------------------------------------------------------------------------

def get_model():
    global _model  # noqa: PLW0603
    if _model is None:
        model_path = current_app.config["MODEL_PATH"]
        if not model_path.exists():
            MODEL_LOADED.set(0)
            raise FileNotFoundError(
                f"Model not found at {model_path}. "
                "Run: python scripts/train_pipeline.py"
            )
        load_start = time.perf_counter()
        _model = joblib.load(model_path)
        load_duration = time.perf_counter() - load_start
        MODEL_LOAD_DURATION.observe(load_duration)
        MODEL_LOADED.set(1)
        logger.info("model loaded", duration_s=round(load_duration, 3), path=str(model_path))
    return _model


# ---------------------------------------------------------------------------
# Prediction logic
# ---------------------------------------------------------------------------

def _validate_url(raw: str) -> tuple[str, str | None]:
    """
    Sanitise and normalise a raw URL string.

    Returns
    -------
    (normalised_url, error_message)
        ``error_message`` is ``None`` when the URL is acceptable.
    """
    url = raw.strip()

    if not url:
        return url, "URL must not be empty."

    if len(url) > 2048:
        return url, "URL exceeds maximum length of 2048 characters."

    if not url.isprintable():
        return url, "URL contains non-printable characters."

    lower = url.lower()
    for dangerous in ("file://", "data:", "javascript:", "vbscript:"):
        if lower.startswith(dangerous):
            return url, f"URL scheme '{dangerous}' is not permitted."

    if not lower.startswith("http"):
        url = "https://" + url

    return url, None


def _analyse_url(url: str) -> dict:
    model = get_model()

    # Time feature extraction separately — useful for identifying slow URLs
    t0 = time.perf_counter()
    features = extract_features(url)
    FEATURE_EXTRACTION_DURATION.observe(time.perf_counter() - t0)

    df = pd.DataFrame([features], columns=FEATURE_NAMES)

    prediction = model.predict(df)[0]
    proba = model.predict_proba(df)[0]

    phishing_pct = round(float(proba[1]) * 100, 2)
    legit_pct = round(float(proba[0]) * 100, 2)
    confidence = round(float(max(proba)) * 100, 2)

    if phishing_pct >= 80:
        risk = "HIGH"
    elif phishing_pct >= 50:
        risk = "MEDIUM"
    elif phishing_pct >= 25:
        risk = "LOW"
    else:
        risk = "SAFE"

    label = "PHISHING" if prediction == 1 else "LEGITIMATE"

    # ── Record prediction metrics ─────────────────────────────────────────
    PREDICTIONS_TOTAL.labels(label=label, risk_level=risk).inc()
    PREDICTION_CONFIDENCE.observe(confidence)
    drift_detector.record(is_phishing=bool(prediction == 1))

    featured_keys = [
        "has_ip", "url_length", "has_shortener", "has_at_symbol",
        "suspicious_tld", "brand_in_subdomain", "encoded_chars",
        "suspicious_keywords", "hyphen_count", "non_standard_port",
    ]
    feature_detail = {
        k: features[FEATURE_NAMES.index(k)]
        for k in featured_keys
        if k in FEATURE_NAMES
    }

    return {
        "url": url,
        "is_phishing": bool(prediction == 1),
        "label": label,
        "phishing_pct": phishing_pct,
        "legit_pct": legit_pct,
        "confidence": confidence,
        "risk_level": risk,
        "features": feature_detail,
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------

@main.route("/")
def index():
    return render_template("index.html")


@main.route("/about")
def about():
    return render_template("about.html")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@main.route("/api/predict", methods=["POST"])
def predict():
    data = request.get_json(silent=True) or {}
    raw_url = data.get("url", "")

    url, err = _validate_url(raw_url)
    if err:
        return jsonify({"error": err}), 400

    try:
        start = time.perf_counter()
        result = _analyse_url(url)
        result["analysis_time_ms"] = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "prediction complete",
            url=url,
            label=result["label"],
            is_phishing=result["is_phishing"],
            confidence=result["confidence"],
            risk_level=result["risk_level"],
            latency_ms=result["analysis_time_ms"],
        )
        return jsonify(result)
    except FileNotFoundError as exc:
        logger.error("model not found", error=str(exc))
        return jsonify({"error": str(exc)}), 503
    except Exception as exc:  # noqa: BLE001
        logger.error("prediction failed", error=str(exc))
        return jsonify({"error": f"Analysis failed: {exc}"}), 500


@main.route("/api/batch", methods=["POST"])
def batch_predict():
    """Analyse up to MAX_BATCH_SIZE URLs in one request."""
    data = request.get_json(silent=True) or {}
    urls = data.get("urls", [])

    if not urls or not isinstance(urls, list):
        return jsonify({"error": "Provide a JSON list under 'urls'"}), 400

    max_batch = current_app.config.get("MAX_BATCH_SIZE", 50)
    if len(urls) > max_batch:
        return jsonify({"error": f"Maximum {max_batch} URLs per batch request"}), 400

    # Record batch size metric before processing
    BATCH_SIZE.observe(len(urls))

    results = []
    for raw in urls:
        url, err = _validate_url(str(raw))
        if err:
            results.append({"url": raw, "error": err})
            continue
        try:
            results.append(_analyse_url(url))
        except Exception as exc:  # noqa: BLE001
            results.append({"url": url, "error": str(exc)})

    phishing_count = sum(1 for r in results if r.get("is_phishing"))
    logger.info(
        "batch prediction complete",
        total=len(results),
        phishing_count=phishing_count,
        legit_count=len(results) - phishing_count,
    )
    return jsonify({"results": results, "total": len(results)})


@main.route("/api/health")
def health():
    try:
        get_model()
        model_loaded = True
    except Exception:  # noqa: BLE001
        model_loaded = False

    return jsonify({
        "status": "ok" if model_loaded else "degraded",
        "model_loaded": model_loaded,
        "num_features": current_app.config.get("NUM_FEATURES"),
    })


# ---------------------------------------------------------------------------
# Prometheus metrics scrape endpoint
# ---------------------------------------------------------------------------

@main.route("/metrics")
def metrics():
    """
    Prometheus scrape endpoint.

    Returns all registered metrics in the Prometheus text exposition format.
    Prometheus scrapes this endpoint every ``scrape_interval`` (default 15s).

    Security note: in production, restrict access to this endpoint to your
    monitoring network only (via Ingress annotations or a NetworkPolicy).
    It does not expose user data, but it does reveal traffic patterns and
    model performance metrics.
    """
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
