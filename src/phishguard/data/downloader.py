"""
phishguard.data.downloader
===========================
Downloads phishing and legitimate URL lists from public sources.

Design decisions
----------------
- Every download function returns a ``set[str]`` of URLs — callers decide
  where to persist them.
- All network calls have explicit timeouts.
- Each source is tried independently; failure of one never aborts others.
- No side effects on import (the original data_creation.py ran code at module
  level, which broke any test that imported it).
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Callable

import requests
import structlog

logger = structlog.get_logger(__name__)

# Default per-source caps to keep training time reasonable.
_PHISHING_CAP = 50_000
_LEGIT_CAP = 50_000
_REQUEST_TIMEOUT_SHORT = 15  # seconds
_REQUEST_TIMEOUT_LONG = 60  # seconds


# ---------------------------------------------------------------------------
# Phishing URL sources
# ---------------------------------------------------------------------------


def _fetch_openphish() -> set[str]:
    r = requests.get("https://openphish.com/feed.txt", timeout=_REQUEST_TIMEOUT_SHORT)
    r.raise_for_status()
    return {line.strip() for line in r.text.splitlines() if line.strip().startswith("http")}


def _fetch_urlhaus() -> set[str]:
    r = requests.get(
        "https://urlhaus.abuse.ch/downloads/csv_recent/",
        timeout=_REQUEST_TIMEOUT_LONG,
    )
    r.raise_for_status()
    urls: set[str] = set()
    for line in r.text.splitlines():
        line = line.strip()
        if line.startswith("#") or not line:
            continue
        parts = line.split('","')
        if len(parts) > 2:
            url = parts[2].strip('"')
            if url.startswith("http"):
                urls.add(url)
    return urls


def _fetch_phishtank() -> set[str]:
    r = requests.get(
        "http://data.phishtank.com/data/online-valid.csv",
        timeout=_REQUEST_TIMEOUT_LONG,
        headers={"User-Agent": "phishtank/python-script"},
    )
    r.raise_for_status()
    reader = csv.DictReader(io.StringIO(r.text))
    return {row["url"].strip() for row in reader if row.get("url", "").strip().startswith("http")}


def _fetch_phishing_database(cap: int) -> set[str]:
    r = requests.get(
        "https://raw.githubusercontent.com/mitchellkrogza/Phishing.Database"
        "/master/phishing-links-ACTIVE.txt",
        timeout=_REQUEST_TIMEOUT_LONG,
        stream=True,
    )
    r.raise_for_status()
    urls: set[str] = set()
    for line in r.iter_lines(decode_unicode=True):
        if len(urls) >= cap:
            break
        line = line.strip()
        if line and not line.startswith("#"):
            if not line.startswith("http"):
                line = "http://" + line
            urls.add(line)
    return urls


def download_phishing_urls(cap: int = _PHISHING_CAP) -> set[str]:
    """
    Fetch phishing URLs from multiple public feeds and return a deduplicated set.

    Parameters
    ----------
    cap:
        Maximum number of URLs to return.

    Returns
    -------
    set[str]
    """
    sources: list[tuple[str, Callable[[], set[str]]]] = [
        ("OpenPhish", _fetch_openphish),
        ("URLhaus", _fetch_urlhaus),
        ("PhishTank", _fetch_phishtank),
        ("Phishing.Database", lambda: _fetch_phishing_database(cap)),
    ]

    all_urls: set[str] = set()
    for name, fetch_fn in sources:
        try:
            before = len(all_urls)
            all_urls |= fetch_fn()
            added = len(all_urls) - before
            logger.info("downloaded from source", source=name, added=added, total=len(all_urls))
        except Exception as exc:  # noqa: BLE001
            logger.warning("source failed", source=name, error=str(exc))

    capped = set(list(all_urls)[:cap])
    logger.info("phishing URLs collected", count=len(capped))
    return capped


# ---------------------------------------------------------------------------
# Legitimate URL sources
# ---------------------------------------------------------------------------


def _fetch_majestic_million(target: int) -> list[str]:
    """Stream the Majestic Million CSV, stop after `target` domains."""
    r = requests.get(
        "https://downloads.majestic.com/majestic_million.csv",
        timeout=_REQUEST_TIMEOUT_LONG,
        stream=True,
    )
    r.raise_for_status()

    domains: list[str] = []
    seen: set[str] = set()
    buf = ""
    first_line = True

    for chunk in r.iter_content(chunk_size=8192, decode_unicode=True):
        buf += chunk
        lines = buf.split("\n")
        buf = lines[-1]
        for line in lines[:-1]:
            if first_line:
                first_line = False
                continue
            parts = line.strip().split(",")
            # CSV format: Rank, TLD, Domain, ...
            if len(parts) >= 3:
                domain = parts[2].strip()
                if domain and domain not in seen:
                    seen.add(domain)
                    domains.append(domain)
            if len(domains) >= target:
                return domains
    return domains


def _fetch_tranco(target: int) -> list[str]:
    r = requests.get("https://tranco-list.eu/top-1m.csv.zip", timeout=_REQUEST_TIMEOUT_LONG)
    r.raise_for_status()
    domains: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        with z.open(z.namelist()[0]) as f:
            for row in csv.reader(io.TextIOWrapper(f)):
                if len(row) >= 2:
                    domain = row[1].strip()
                    if domain and domain not in seen:
                        seen.add(domain)
                        domains.append(domain)
                if len(domains) >= target:
                    break
    return domains


def download_legitimate_urls(target: int = _LEGIT_CAP) -> list[str]:
    """
    Fetch legitimate domain names from public lists and return them as https:// URLs.

    Parameters
    ----------
    target:
        Number of URLs to return.

    Returns
    -------
    list[str]
        URLs in the form ``"https://domain.tld"``.
    """
    domains: list[str] = []

    sources: list[tuple[str, Callable[[int], list[str]]]] = [
        ("Majestic Million", _fetch_majestic_million),
        ("Tranco", _fetch_tranco),
    ]

    for name, fetch_fn in sources:
        if len(domains) >= target:
            break
        remaining = target - len(domains)
        try:
            before = len(domains)
            new = fetch_fn(remaining)
            existing = {d.replace("https://", "") for d in domains}
            for d in new:
                if d not in existing:
                    existing.add(d)
                    domains.append(d)
            logger.info(
                "downloaded from source",
                source=name,
                added=len(domains) - before,
                total=len(domains),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("source failed", source=name, error=str(exc))

    legit_urls = [f"https://{d}" for d in domains[:target]]
    logger.info("legitimate URLs collected", count=len(legit_urls))
    return legit_urls
