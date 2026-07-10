"""
tests/test_logging.py
=====================
Tests for the logging and request-ID middleware layer.

What we verify
--------------
- Every response carries an ``X-Request-ID`` header.
- A client-supplied ``X-Request-ID`` is echoed back unchanged.
- ``configure_logging`` can be called multiple times without raising
  (idempotency matters because the test suite creates multiple app instances).
- The health, predict, and batch endpoints all set the header.
"""

from __future__ import annotations

import json

from phishguard.logging_config import configure_logging

# ---------------------------------------------------------------------------
# configure_logging idempotency
# ---------------------------------------------------------------------------


class TestConfigureLogging:
    def test_dev_config_does_not_raise(self):
        configure_logging(env="development")

    def test_prod_config_does_not_raise(self):
        configure_logging(env="production")

    def test_testing_config_does_not_raise(self):
        configure_logging(env="testing")

    def test_calling_twice_is_safe(self):
        configure_logging(env="development")
        configure_logging(env="development")


# ---------------------------------------------------------------------------
# X-Request-ID header propagation
# ---------------------------------------------------------------------------


class TestRequestId:
    def test_health_has_request_id_header(self, client):
        resp = client.get("/api/health")
        assert "X-Request-ID" in resp.headers

    def test_predict_has_request_id_header(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": "https://google.com"}),
            content_type="application/json",
        )
        assert "X-Request-ID" in resp.headers

    def test_batch_has_request_id_header(self, client):
        resp = client.post(
            "/api/batch",
            data=json.dumps({"urls": ["https://google.com"]}),
            content_type="application/json",
        )
        assert "X-Request-ID" in resp.headers

    def test_request_id_is_non_empty(self, client):
        resp = client.get("/api/health")
        assert len(resp.headers["X-Request-ID"]) > 0

    def test_client_supplied_request_id_is_echoed(self, client):
        custom_id = "my-trace-id-abc123"
        resp = client.get("/api/health", headers={"X-Request-ID": custom_id})
        assert resp.headers["X-Request-ID"] == custom_id

    def test_each_request_gets_unique_id(self, client):
        ids = {client.get("/api/health").headers["X-Request-ID"] for _ in range(5)}
        assert len(ids) == 5  # all five must be distinct

    def test_error_response_still_has_request_id(self, client):
        resp = client.post(
            "/api/predict",
            data=json.dumps({"url": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        assert "X-Request-ID" in resp.headers
