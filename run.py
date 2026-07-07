#!/usr/bin/env python3
"""
Entry point — start the Flask development server or production gunicorn process.

Usage
-----
    python run.py               # development (Flask dev server)
    python run.py --prod        # production (gunicorn, reads PORT env var)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

from app import create_app
from app.config import DevelopmentConfig, ProductionConfig

app = create_app(DevelopmentConfig)

# Logger is available after create_app() calls configure_logging()
import structlog  # noqa: E402 — must come after create_app
_log = structlog.get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="PhishGuard URL Detection API")
    parser.add_argument("--prod", action="store_true", help="Run in production mode via gunicorn")
    args = parser.parse_args()

    global app
    if args.prod:
        ProductionConfig.validate()
        app = create_app(ProductionConfig)
        config = ProductionConfig
    else:
        app = create_app(DevelopmentConfig)
        config = DevelopmentConfig

    port = int(os.environ.get("PORT", 5005))

    if args.prod:
        workers = int(os.environ.get("WEB_CONCURRENCY", 2))
        _log.info("starting production server", host="0.0.0.0", port=port, workers=workers)
        cmd = [
            sys.executable, "-m", "gunicorn",
            "--bind", f"0.0.0.0:{port}",
            "--workers", str(workers),
            "--timeout", "120",
            "run:app",
        ]
        subprocess.run(cmd, check=True)
    else:
        _log.info("starting development server", host="127.0.0.1", port=port)
        app.run(host="0.0.0.0", port=port, debug=config.DEBUG)


if __name__ == "__main__":
    main()
