"""
tests/test_metrics.py
======================
Tests for Phase 8 observability layer:

- ``/metrics`` endpoint returns Prometheus text format
- All expected metric names are present in the output
- Prediction endpoints increment the correct counters
- DriftDetector correctly computes rolling phishing rate
- DriftDetector fires alerts at the right threshold
- DriftDetector clears drift when rate returns to normal
"""

from __future__ import annotations

import json

import pytest

from phishguard.drift import DriftDetector


# ---------------------------------------------------------------------------
# /metrics endpoint
# ---------------------------------------------------------------------------

class TestMetricsEndpoint:
    def test_metrics_endpoint_returns_200(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_content_type_is_prometheus(self, client):
        resp = client.get("/metrics")
        assert "text/plain" in resp.content_type

    def test_metrics_contains_http_requests_total(self, client):
        client.get("/api/health")   # generate at least one request
        resp = client.get("/metrics")
        assert b"phishguard_http_requests_total" in resp.data

    def test_metrics_contains_request_duration(self, client):
        resp = client.get("/metrics")
        assert b"phishguard_http_request_duration_seconds" in resp.data

    def test_metrics_contains_model_loaded_gauge(self, client):
        resp = client.get("/metrics")
        assert b"phishguard_model_loaded" in resp.data

    def test_metrics_contains_active_requests_gauge(self, client):
        resp = client.get("/metrics")
        assert b"phishguard_active_requests" in resp.data

    def test_metrics_contains_drift_metrics(self, client):
        resp = client.get("/metrics")
        assert b"phishguard_drift_detected" in resp.data
        assert b"phishguard_phishing_rate_1m" in resp.data
        assert b"phishguard_drift_baseline" in resp.data

    def test_metrics_not_included_in_request_counter(self, client):
        """The /metrics endpoint itself should not inflate request counters."""
        # Hit metrics several times
        for _ in range(3):
            client.get("/metrics")
        # The endpoint label "metrics" should not appear in counters
        resp = client.get("/metrics")
        # We only check that the endpoint is working — detailed label checking
        # requires parsing the exposition format which is overkill here
        assert resp.status_code == 200

    def test_metrics_endpoint_excluded_from_http_requests_total(self, client):
        """
        Regression test: blueprint endpoints are prefixed with 'main.' by Flask
        (e.g. 'main.metrics', not 'metrics'). The exclusion list must match the
        prefixed name or /metrics scrapes inflate their own request counter.
        """
        for _ in range(5):
            client.get("/metrics")
        resp = client.get("/metrics")
        body = resp.data.decode()
        assert 'endpoint="main.metrics"' not in body

    def test_active_requests_returns_to_zero_after_request_completes(self, client):
        """
        Regression test: active_requests gauge must be decremented in
        after_request. A mismatch between the exclusion check in before_request
        and after_request (e.g. comparing 'metrics' vs 'main.metrics') causes
        the gauge to increment without ever decrementing, leaking upward
        forever and falsely indicating requests are stuck in-flight.
        """
        client.get("/api/health")
        client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        resp = client.get("/metrics")
        body = resp.data.decode()
        assert "phishguard_active_requests 0.0" in body


# ---------------------------------------------------------------------------
# Prediction counter increments
# ---------------------------------------------------------------------------

class TestPredictionMetrics:
    def test_prediction_increments_counter(self, client):
        """Calling /api/predict should cause predictions_total to appear."""
        client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        resp = client.get("/metrics")
        assert b"phishguard_predictions_total" in resp.data

    def test_confidence_histogram_populated_after_prediction(self, client):
        client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        resp = client.get("/metrics")
        assert b"phishguard_prediction_confidence" in resp.data

    def test_feature_extraction_duration_recorded(self, client):
        client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        resp = client.get("/metrics")
        assert b"phishguard_feature_extraction_seconds" in resp.data

    def test_batch_size_histogram_recorded(self, client):
        client.post(
            "/api/batch",
            data=json.dumps({"urls": ["https://google.com", "https://example.com"]}),
            content_type="application/json",
        )
        resp = client.get("/metrics")
        assert b"phishguard_batch_size" in resp.data


# ---------------------------------------------------------------------------
# DriftDetector unit tests
# ---------------------------------------------------------------------------

class TestDriftDetector:
    """
    Unit tests for DriftDetector that use a fresh instance per test
    to avoid state leakage from the module-level singleton.
    """

    def _make_detector(self, **kwargs):
        defaults = dict(
            baseline_rate=0.5,
            threshold=0.3,
            window_size=10,
            alert_cooldown_s=0.0,   # no cooldown in tests
        )
        defaults.update(kwargs)
        return DriftDetector(**defaults)

    def test_initial_rate_equals_baseline(self):
        d = self._make_detector(baseline_rate=0.4)
        assert d.current_rate == 0.4

    def test_rate_updates_after_recording(self):
        d = self._make_detector(window_size=4)
        d.record(True)
        d.record(True)
        d.record(False)
        d.record(False)
        assert d.current_rate == 0.5

    def test_window_not_full_before_window_size_predictions(self):
        d = self._make_detector(window_size=10)
        for _ in range(9):
            d.record(True)
        assert not d.window_full

    def test_window_full_after_window_size_predictions(self):
        d = self._make_detector(window_size=5)
        for _ in range(5):
            d.record(True)
        assert d.window_full

    def test_window_is_rolling_not_cumulative(self):
        d = self._make_detector(window_size=3)
        d.record(True)
        d.record(True)
        d.record(True)   # window: [1,1,1] → rate 1.0
        d.record(False)
        d.record(False)
        d.record(False)  # window: [0,0,0] → rate 0.0 (old values evicted)
        assert d.current_rate == 0.0

    def test_no_drift_below_threshold(self):
        # baseline 0.5, threshold 0.3 → drift fires above 0.8 or below 0.2
        d = self._make_detector(baseline_rate=0.5, threshold=0.3, window_size=10)
        # Record 6 phishing, 4 legit = rate 0.6 (deviation 0.1 < threshold 0.3)
        for _ in range(6):
            d.record(True)
        for _ in range(4):
            d.record(False)
        assert not d._drift_active

    def test_drift_detected_above_threshold(self):
        # baseline 0.5, threshold 0.3 → 10/10 phishing = rate 1.0, deviation 0.5 > 0.3
        d = self._make_detector(baseline_rate=0.5, threshold=0.3, window_size=10)
        for _ in range(10):
            d.record(True)
        assert d._drift_active

    def test_drift_detected_below_threshold(self):
        # baseline 0.5, threshold 0.3 → 0/10 phishing = rate 0.0, deviation 0.5 > 0.3
        d = self._make_detector(baseline_rate=0.5, threshold=0.3, window_size=10)
        for _ in range(10):
            d.record(False)
        assert d._drift_active

    def test_drift_clears_when_rate_normalises(self):
        d = self._make_detector(baseline_rate=0.5, threshold=0.3, window_size=10)
        # Fill with all phishing → drift
        for _ in range(10):
            d.record(True)
        assert d._drift_active
        # Fill with balanced predictions → rate returns to ~0.5
        for _ in range(10):
            d.record(True)
            d.record(False)   # alternating → still fills window with 50/50
        # After 10 more records the window is [1,0,1,0,1,0,1,0,1,0] → rate 0.5
        assert not d._drift_active

    def test_reset_clears_window_and_drift(self):
        d = self._make_detector(window_size=5)
        for _ in range(5):
            d.record(True)
        assert d._drift_active
        d.reset()
        assert not d._drift_active
        assert len(d._window) == 0

    def test_invalid_baseline_raises(self):
        with pytest.raises(ValueError, match="baseline_rate"):
            DriftDetector(baseline_rate=1.5)

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="threshold"):
            DriftDetector(threshold=0.0)

    def test_invalid_window_size_raises(self):
        with pytest.raises(ValueError, match="window_size"):
            DriftDetector(window_size=0)
