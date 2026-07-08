"""
tests/test_routes_coverage.py
==============================
Targeted tests for uncovered branches in app/routes.py:

- 503 when model file is missing (get_model FileNotFoundError path)
- 500 when analysis raises an unexpected exception
- Health endpoint returns ``degraded`` when model is missing
- Batch endpoint propagates per-item errors without failing the whole batch
- Non-printable character URL validation
- vbscript: dangerous scheme
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app import create_app
from app.config import TestingConfig


# ---------------------------------------------------------------------------
# Fixture: app with NO model file (model_path points to a non-existent file)
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_no_model(tmp_path):
    class _NoModelConfig(TestingConfig):
        MODEL_PATH = tmp_path / "does_not_exist.joblib"

    application = create_app(_NoModelConfig)
    return application


@pytest.fixture()
def client_no_model(app_no_model):
    import app.routes as routes_module
    # Reset the module-level model cache so the no-model app doesn't
    # accidentally use a model loaded by a previous test.
    original = routes_module._model
    routes_module._model = None
    yield app_no_model.test_client()
    routes_module._model = original


# ---------------------------------------------------------------------------
# Model-not-found paths (503)
# ---------------------------------------------------------------------------

class TestModelNotFound:
    def test_predict_returns_503_when_model_missing(self, client_no_model):
        resp = client_no_model.post(
            "/api/predict",
            data=json.dumps({"url": "https://example.com"}),
            content_type="application/json",
        )
        assert resp.status_code == 503
        assert "error" in resp.get_json()

    def test_health_returns_degraded_when_model_missing(self, client_no_model):
        resp = client_no_model.get("/api/health")
        data = resp.get_json()
        assert data["status"] == "degraded"
        assert data["model_loaded"] is False

    def test_health_still_returns_200_when_degraded(self, client_no_model):
        # /api/health should always return 200 — it's a health check, not a
        # prediction endpoint.  A 503 here would cause k8s to kill the pod.
        resp = client_no_model.get("/api/health")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Unexpected exception in _analyse_url (500 path)
# ---------------------------------------------------------------------------

class TestAnalyseUrlException:
    def test_predict_returns_500_on_unexpected_exception(self, client):
        with patch(
            "app.routes._analyse_url",
            side_effect=RuntimeError("something went wrong internally"),
        ):
            resp = client.post(
                "/api/predict",
                data=json.dumps({"url": "https://example.com"}),
                content_type="application/json",
            )
        assert resp.status_code == 500
        data = resp.get_json()
        assert "error" in data


# ---------------------------------------------------------------------------
# Batch: per-item error handling (invalid URL inside a valid batch)
# ---------------------------------------------------------------------------

class TestBatchItemErrors:
    def test_invalid_url_in_batch_does_not_abort_batch(self, client):
        """A bad URL in the middle should produce an error entry, not a 400."""
        resp = client.post(
            "/api/batch",
            data=json.dumps({
                "urls": [
                    "https://google.com",
                    "",                       # ← invalid: empty
                    "https://example.com",
                ]
            }),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        # The empty URL entry must have an "error" key
        empty_result = data["results"][1]
        assert "error" in empty_result

    def test_batch_with_all_invalid_urls_returns_all_errors(self, client):
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": ["", "   ", "file:///etc/passwd"]}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = resp.get_json()
        for result in data["results"]:
            assert "error" in result

    def test_batch_exception_in_analysis_captured_per_item(self, client):
        """If _analyse_url raises for one item, that item gets an error entry."""
        call_count = 0

        def side_effect(url):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("analysis exploded")
            from app.routes import _analyse_url as real
            # We patched _analyse_url, so we need to call the original logic.
            # Simplest: return a fake result dict for non-exploding calls.
            return {
                "url": url, "is_phishing": False, "label": "LEGITIMATE",
                "phishing_pct": 10.0, "legit_pct": 90.0, "confidence": 90.0,
                "risk_level": "SAFE", "features": {},
            }

        with patch("app.routes._analyse_url", side_effect=side_effect):
            resp = client.post(
                "/api/batch",
                data=json.dumps({"urls": ["https://a.com", "https://b.com", "https://c.com"]}),
                content_type="application/json",
            )

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 3
        assert "error" in data["results"][1]


# ---------------------------------------------------------------------------
# URL validation edge cases
# ---------------------------------------------------------------------------

class TestUrlValidationEdgeCases:
    def test_non_printable_chars_return_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://evil.com/\x00payload"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "non-printable" in resp.get_json()["error"].lower()

    def test_vbscript_scheme_returns_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "vbscript:msgbox(1)"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_url_with_only_whitespace_returns_400(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "   "}),
            content_type="application/json",
        )
        # After strip() the URL is empty → "must not be empty" error
        assert resp.status_code == 400

    def test_no_json_body_returns_400(self, client):
        resp = client.post("/api/predict", data="not json", content_type="text/plain")
        assert resp.status_code == 400
