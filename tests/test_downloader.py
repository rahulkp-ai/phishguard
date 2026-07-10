"""
tests/test_downloader.py
=========================
Unit tests for ``phishguard.data.downloader``.

All HTTP calls are mocked — these are fast unit tests, not integration tests.
No network access required.

Why this file exists
---------------------
Before this file, `download_phishing_urls()` and `download_legitimate_urls()`
had zero test coverage because they require network access and were
correctly excluded from the coverage gate (see pyproject.toml). But that
meant a real bug shipped silently: the module used `logging.getLogger()`
(stdlib) while every log call used structlog's `key=value` keyword-argument
style (`logger.info("msg", source=name, added=5)`). Stdlib's `Logger.info()`
does not accept arbitrary kwargs — every single source in the loop crashed
with `TypeError: Logger._log() got an unexpected keyword argument 'source'`,
even on a successful download, because the *success* log line used the same
broken call style as the failure line.

The bug was invisible to pytest because nothing exercised these functions —
mocking the network calls here closes that gap permanently.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from phishguard.data.downloader import (
    download_legitimate_urls,
    download_phishing_urls,
)


def _mock_response(text: str = "", json_data=None, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(f"{status_code} error")
    return resp


# ---------------------------------------------------------------------------
# Regression test — the exact crash from production
# ---------------------------------------------------------------------------


class TestLoggingDoesNotCrash:
    """
    Regression tests pinning the exact failure mode reported in production:

        TypeError: Logger._log() got an unexpected keyword argument 'source'

    These tests mock the HTTP layer so they run with zero network access,
    but they exercise the REAL logger calls inside download_phishing_urls()
    and download_legitimate_urls() — both the success-path log line and the
    failure-path log line, since the original bug affected both.
    """

    @patch("phishguard.data.downloader._fetch_openphish")
    @patch("phishguard.data.downloader._fetch_urlhaus")
    @patch("phishguard.data.downloader._fetch_phishtank")
    @patch("phishguard.data.downloader._fetch_phishing_database")
    def test_success_path_logging_does_not_raise(
        self, mock_db, mock_phishtank, mock_urlhaus, mock_openphish
    ):
        """The success-path logger.info(source=..., added=..., total=...) call
        must not raise — this is the exact line that crashed in production."""
        mock_openphish.return_value = {"http://evil1.com", "http://evil2.com"}
        mock_urlhaus.return_value = {"http://evil3.com"}
        mock_phishtank.return_value = set()
        mock_db.return_value = set()

        # Must complete without raising TypeError
        result = download_phishing_urls(cap=100)
        assert isinstance(result, set)
        assert len(result) > 0

    @patch("phishguard.data.downloader._fetch_openphish")
    @patch("phishguard.data.downloader._fetch_urlhaus")
    @patch("phishguard.data.downloader._fetch_phishtank")
    @patch("phishguard.data.downloader._fetch_phishing_database")
    def test_failure_path_logging_does_not_raise(
        self, mock_db, mock_phishtank, mock_urlhaus, mock_openphish
    ):
        """The failure-path logger.warning(source=..., error=...) call
        must not raise when a source fails — this is what crashed the
        real training pipeline run (every source failed → every warning crashed)."""
        mock_openphish.side_effect = requests.ConnectionError("DNS resolution failed")
        mock_urlhaus.side_effect = requests.Timeout("read timeout")
        mock_phishtank.side_effect = requests.HTTPError("403 Forbidden")
        mock_db.side_effect = Exception("unexpected error")

        # All four sources fail — must still return an empty set, not raise
        result = download_phishing_urls(cap=100)
        assert result == set()

    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_legit_urls_success_path_logging_does_not_raise(self, mock_tranco, mock_majestic):
        mock_majestic.return_value = ["google.com", "github.com"]
        mock_tranco.return_value = ["stackoverflow.com"]

        result = download_legitimate_urls(target=10)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(u.startswith("https://") for u in result)

    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_legit_urls_failure_path_logging_does_not_raise(self, mock_tranco, mock_majestic):
        mock_majestic.side_effect = requests.ConnectionError("DNS failure")
        mock_tranco.side_effect = requests.Timeout("timeout")

        result = download_legitimate_urls(target=10)
        assert result == []


# ---------------------------------------------------------------------------
# Behavioural tests — correctness of dedup, capping, error isolation
# ---------------------------------------------------------------------------


class TestDownloadPhishingUrls:
    @patch("phishguard.data.downloader._fetch_openphish")
    @patch("phishguard.data.downloader._fetch_urlhaus")
    @patch("phishguard.data.downloader._fetch_phishtank")
    @patch("phishguard.data.downloader._fetch_phishing_database")
    def test_deduplicates_across_sources(
        self, mock_db, mock_phishtank, mock_urlhaus, mock_openphish
    ):
        # Same URL returned by two sources — must appear once in the result
        mock_openphish.return_value = {"http://evil.com"}
        mock_urlhaus.return_value = {"http://evil.com"}
        mock_phishtank.return_value = set()
        mock_db.return_value = set()

        result = download_phishing_urls(cap=100)
        assert result == {"http://evil.com"}

    @patch("phishguard.data.downloader._fetch_openphish")
    @patch("phishguard.data.downloader._fetch_urlhaus")
    @patch("phishguard.data.downloader._fetch_phishtank")
    @patch("phishguard.data.downloader._fetch_phishing_database")
    def test_respects_cap(self, mock_db, mock_phishtank, mock_urlhaus, mock_openphish):
        mock_openphish.return_value = {f"http://evil{i}.com" for i in range(50)}
        mock_urlhaus.return_value = set()
        mock_phishtank.return_value = set()
        mock_db.return_value = set()

        result = download_phishing_urls(cap=10)
        assert len(result) <= 10

    @patch("phishguard.data.downloader._fetch_openphish")
    @patch("phishguard.data.downloader._fetch_urlhaus")
    @patch("phishguard.data.downloader._fetch_phishtank")
    @patch("phishguard.data.downloader._fetch_phishing_database")
    def test_one_source_failing_does_not_block_others(
        self, mock_db, mock_phishtank, mock_urlhaus, mock_openphish
    ):
        mock_openphish.side_effect = requests.ConnectionError("down")
        mock_urlhaus.return_value = {"http://evil.com"}
        mock_phishtank.return_value = set()
        mock_db.return_value = set()

        result = download_phishing_urls(cap=100)
        assert result == {"http://evil.com"}


class TestDownloadLegitimateUrls:
    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_returns_https_urls(self, mock_tranco, mock_majestic):
        mock_majestic.return_value = ["example.com"]
        mock_tranco.return_value = []

        result = download_legitimate_urls(target=5)
        assert result == ["https://example.com"]

    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_deduplicates_across_sources(self, mock_tranco, mock_majestic):
        mock_majestic.return_value = ["example.com"]
        mock_tranco.return_value = ["example.com", "other.com"]

        result = download_legitimate_urls(target=10)
        domains = {u.replace("https://", "") for u in result}
        assert domains == {"example.com", "other.com"}

    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_respects_target_count(self, mock_tranco, mock_majestic):
        mock_majestic.return_value = [f"site{i}.com" for i in range(20)]
        mock_tranco.return_value = []

        result = download_legitimate_urls(target=5)
        assert len(result) <= 5

    @patch("phishguard.data.downloader._fetch_majestic_million")
    @patch("phishguard.data.downloader._fetch_tranco")
    def test_skips_remaining_sources_once_target_reached(self, mock_tranco, mock_majestic):
        mock_majestic.return_value = [f"site{i}.com" for i in range(10)]

        download_legitimate_urls(target=5)
        # Tranco should never be called since Majestic alone satisfied the target
        mock_tranco.assert_not_called()
