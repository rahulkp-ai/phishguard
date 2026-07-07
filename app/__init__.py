"""Flask application factory."""

from __future__ import annotations

from flask import Flask

from .config import Config


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ------------------------------------------------------------------
    # Logging — must be configured before any logger is used.
    # ------------------------------------------------------------------
    from phishguard.logging_config import configure_logging  # noqa: PLC0415

    env = "testing" if app.config.get("TESTING") else (
        "development" if app.config.get("DEBUG") else "production"
    )
    configure_logging(env=env)

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from .routes import main  # noqa: PLC0415

    app.register_blueprint(main)

    # ------------------------------------------------------------------
    # Request lifecycle logging + request ID middleware
    # ------------------------------------------------------------------
    from .middleware import register_request_logging  # noqa: PLC0415

    register_request_logging(app)

    # ------------------------------------------------------------------
    # Prometheus metrics instrumentation
    # ------------------------------------------------------------------
    from .metrics_middleware import register_metrics_middleware  # noqa: PLC0415

    register_metrics_middleware(app)

    return app
