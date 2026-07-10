"""
scripts/train_pipeline.py
==========================
One-command full pipeline: download → build dataset → train model.

    python scripts/train_pipeline.py            # full run
    python scripts/train_pipeline.py --skip-download  # reuse existing URL files

This script is a thin orchestrator.  All business logic lives in the
``phishguard`` package — this file only wires paths and calls functions.
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — call configure_logging before any phishguard imports
# so every submodule's logger is configured from the start.
# ---------------------------------------------------------------------------
from phishguard.logging_config import configure_logging

configure_logging(env="development", level="INFO")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path constants (all relative to project root)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"

PHISHING_TXT = PROCESSED / "phishing_urls.txt"
LEGIT_TXT = PROCESSED / "legitimate_urls.txt"
DATASET_CSV = PROCESSED / "url_dataset.csv"
MODEL_PATH = MODELS / "phishing_model.joblib"

PROCESSED.mkdir(parents=True, exist_ok=True)
MODELS.mkdir(parents=True, exist_ok=True)


def _header(step: int, title: str) -> None:
    logger.info("=" * 55)
    logger.info("  STEP %d — %s", step, title)
    logger.info("=" * 55)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(description="PhishGuard training pipeline")
parser.add_argument(
    "--skip-download",
    action="store_true",
    help="Skip URL download; reuse existing phishing_urls.txt and legitimate_urls.txt",
)
parser.add_argument("--cap", type=int, default=25_000, help="Max URLs per class (default 25000)")
args = parser.parse_args()


# ---------------------------------------------------------------------------
# Step 1: Download URLs
# ---------------------------------------------------------------------------
if args.skip_download:
    logger.info("Skipping download — using existing URL files.")
    if not PHISHING_TXT.exists() or not LEGIT_TXT.exists():
        raise FileNotFoundError(
            "--skip-download specified but URL files are missing.\n"
            f"Expected:\n  {PHISHING_TXT}\n  {LEGIT_TXT}"
        )
else:
    _header(1, "Downloading URL data")
    t0 = time.perf_counter()

    from phishguard.data.downloader import download_legitimate_urls, download_phishing_urls

    phishing_urls = download_phishing_urls(cap=args.cap)
    PHISHING_TXT.write_text("\n".join(phishing_urls) + "\n")
    logger.info("Phishing URLs written → %s", PHISHING_TXT)

    legit_urls = download_legitimate_urls(target=min(len(phishing_urls), args.cap))
    LEGIT_TXT.write_text("\n".join(legit_urls) + "\n")
    logger.info("Legitimate URLs written → %s", LEGIT_TXT)

    logger.info("Download complete in %.1fs", time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Step 2: Build feature dataset
# ---------------------------------------------------------------------------
_header(2, "Extracting features")
t0 = time.perf_counter()

from phishguard.data.builder import build_dataset  # noqa: E402

df = build_dataset(PHISHING_TXT, LEGIT_TXT, DATASET_CSV)
logger.info("Feature extraction complete in %.1fs  shape=%s", time.perf_counter() - t0, df.shape)


# ---------------------------------------------------------------------------
# Step 3: Train model
# ---------------------------------------------------------------------------
_header(3, "Training Random Forest")
t0 = time.perf_counter()

from phishguard.models.trainer import train  # noqa: E402

metrics = train(DATASET_CSV, MODEL_PATH)
logger.info(
    "Training complete in %.1fs  accuracy=%.4f  roc_auc=%.4f",
    time.perf_counter() - t0,
    metrics["accuracy"],
    metrics["roc_auc"],
)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
logger.info("=" * 55)
logger.info("  PIPELINE COMPLETE")
logger.info("  Model → %s", MODEL_PATH)
logger.info("  Run:    python run.py")
logger.info("  Open:   http://localhost:5000")
logger.info("=" * 55)
