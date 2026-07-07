"""
Flask application configuration.

Secret key
----------
The fallback value is intentionally empty in production — if SECRET_KEY is not
set in the environment, Flask will raise a RuntimeError on startup rather than
silently using a predictable key.  In development the fallback is a clearly
labelled dev-only string so it's obvious when the real env var is missing.
"""

from __future__ import annotations

import os
from pathlib import Path

# Repository root — two levels up from this file (app/config.py → app/ → root)
_ROOT = Path(__file__).resolve().parent.parent


class Config:
    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------
    # In production this MUST be set as an environment variable.
    # An empty fallback ensures startup fails loudly rather than using a
    # known-public string.
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "")

    # ------------------------------------------------------------------
    # Model
    # ------------------------------------------------------------------
    MODEL_PATH: Path = Path(
        os.environ.get("MODEL_PATH", str(_ROOT / "models" / "phishing_model.joblib"))
    )

    # ------------------------------------------------------------------
    # Feature count — used in routes to validate the loaded model
    # ------------------------------------------------------------------
    NUM_FEATURES: int = 28

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    DEBUG: bool = False
    TESTING: bool = False
    MAX_BATCH_SIZE: int = 50


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "dev-only-secret-do-not-use-in-prod")


class ProductionConfig(Config):
    DEBUG = False

    @classmethod
    def validate(cls) -> None:
        """Raise if required production config is missing."""
        if not cls.SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY environment variable is not set. "
                "Set it before starting the production server."
            )


class TestingConfig(Config):
    TESTING = True
    DEBUG = True
    SECRET_KEY: str = "testing-secret"
    # Tests supply their own model path via the fixture in conftest.py
