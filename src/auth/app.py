"""Application factory for the auth microservice."""

from __future__ import annotations

from flask import Flask

from .config import Config, TestConfig
from common.extensions import bcrypt, db, jwt, redis_manager
from .routes import bp as auth_blueprint


def _create_app(config_object) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    redis_manager.init_app(app)

    with app.app_context():
        db.create_all()

    app.register_blueprint(auth_blueprint)
    return app


def create_app() -> Flask:
    return _create_app(Config())


def create_test_app() -> Flask:
    return _create_app(TestConfig())


if __name__ == "__main__":  # pragma: no cover
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
