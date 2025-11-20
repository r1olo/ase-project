"""Application factory for the Card Catalogue microservice."""
from __future__ import annotations
from .config import Config, TestConfig
from .routes import catalogue as catalogue_blueprint
from common.app_factory import create_flask_app
from common.extensions import db
from flask import Flask

def _init_cards_db():
    pass

def _create_app(config) -> Flask:
    return create_flask_app(
        name=__name__,
        config_obj=config,
        extensions=(db),
        blueprints=(catalogue_blueprint),
        init_app_context_steps=(_init_cards_db)
    )

def create_app() -> Flask:
    return _create_app(Config())

def create_test_app() -> Flask:
    return _create_app(TestConfig())

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
