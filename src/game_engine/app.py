"""Application factory for the game engine service."""

from __future__ import annotations

from flask import Flask

from .config import Config, TestConfig
from .extensions import db
from .routes import bp as engine_blueprint


def _create_app(config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.register_blueprint(engine_blueprint)
    return app


def create_app() -> Flask:
    return _create_app(Config())


def create_test_app() -> Flask:
    return _create_app(TestConfig())


if __name__ == "__main__":  # pragma: no cover
    create_app().run(host="0.0.0.0", port=5003)
