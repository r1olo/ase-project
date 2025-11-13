"""Application factory for the matchmaking service."""

from __future__ import annotations

from flask import Flask

from .config import Config, TestConfig
from .routes import bp as matchmaking_blueprint


def _create_app(config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)
    app.register_blueprint(matchmaking_blueprint)
    return app


def create_app() -> Flask:
    return _create_app(Config())


def create_test_app() -> Flask:
    return _create_app(TestConfig())


if __name__ == "__main__":  # pragma: no cover
    create_app().run(host="0.0.0.0", port=5004)
