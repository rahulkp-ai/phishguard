"""
tests/test_routes.py
====================
Integration tests for Flask API endpoints.

Uses the ``client`` fixture from conftest.py, which spins up the Flask
test client with a tiny in-memory model — no real model file needed.
"""

from __future__ import annotations

import json

import pytest

# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "ok"
        assert data["model_loaded"] is True

    def test_health_returns_num_features(self, client):
        data = client.get("/api/health").get_json()
        assert data["num_features"] == 28


# ---------------------------------------------------------------------------
# Single-predict endpoint
# ---------------------------------------------------------------------------


class TestPredict:
    def test_predict_returns_200(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://google.com"}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_predict_response_shape(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://google.com"}),
            content_type="application/json",
        )
        data = resp.get_json()
        required_keys = {
            "url",
            "is_phishing",
            "label",
            "phishing_pct",
            "legit_pct",
            "confidence",
            "risk_level",
            "features",
            "analysis_time_ms",
        }
        assert required_keys.issubset(data.keys())

    def test_predict_label_values(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["label"] in {"PHISHING", "LEGITIMATE"}

    def test_predict_risk_level_values(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["risk_level"] in {"HIGH", "MEDIUM", "LOW", "SAFE"}

    def test_predict_probabilities_sum_to_100(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        data = resp.get_json()
        total = data["phishing_pct"] + data["legit_pct"]
        assert abs(total - 100.0) < 0.1

    def test_predict_auto_adds_scheme(self, client):
        """URLs without a scheme should have https:// added automatically."""
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "example.com"}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["url"].startswith("https://")

    def test_predict_empty_url_returns_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_predict_missing_url_returns_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_predict_url_too_long_returns_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com/" + "a" * 3000}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    @pytest.mark.parametrize(
        "dangerous",
        [
            "file:///etc/passwd",
            "data:text/html,<script>alert(1)</script>",
            "javascript:alert(1)",
        ],
    )
    def test_predict_dangerous_scheme_returns_400(self, client, dangerous):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": dangerous}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Batch endpoint
# ---------------------------------------------------------------------------


class TestBatch:
    def test_batch_returns_200(self, client):
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": ["https://google.com", "https://example.com"]}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_batch_result_count(self, client):
        urls = ["https://google.com", "https://example.com", "http://evil.tk/login"]
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": urls}),
            content_type="application/json",
        )
        data = resp.get_json()
        assert data["total"] == 3
        assert len(data["results"]) == 3

    def test_batch_too_many_urls_returns_400(self, client):
        urls = [f"https://example{i}.com" for i in range(51)]
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": urls}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_empty_list_returns_400(self, client):
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": []}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_batch_missing_urls_key_returns_400(self, client):
        resp = client.post(
            "/api/batch",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------


class TestPages:
    def test_index_returns_200(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_about_returns_200(self, client):
        resp = client.get("/about")
        assert resp.status_code == 200
