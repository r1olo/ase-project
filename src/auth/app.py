"""Application factory for the auth microservice."""

from __future__ import annotations

from flask import Flask

from .config import Config, TestConfig
from common.app_factory import create_flask_app
from common.extensions import bcrypt, db, jwt, redis_manager
from .routes import bp as auth_blueprint


def _create_app(config_object) -> Flask:
    return create_flask_app(
        config_obj=config_object,
        extensions=(db, bcrypt, jwt, redis_manager),
        blueprints=(auth_blueprint,),
        init_app_context_steps=(lambda _app: db.create_all(),),
    )


def create_app() -> Flask:
    return _create_app(Config())


def create_test_app() -> Flask:
    return _create_app(TestConfig())


if __name__ == "__main__":  # pragma: no cover
    app = create_app()
    app.run(host="0.0.0.0", port=5000)
