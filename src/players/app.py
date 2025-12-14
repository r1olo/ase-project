"""Application factory for the players microservice."""

from __future__ import annotations

from flask import Flask

from .config import Config, TestConfig
from common.extensions import db, jwt  
from .routes import bp as players_blueprint


def _create_app(config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    # --- Inizializzazione Estensioni ---
    db.init_app(app)
    jwt.init_app(app) 

    with app.app_context():
        db.create_all()

    app.register_blueprint(players_blueprint)
    return app


def create_app() -> Flask:
    return _create_app(Config())


def create_test_app() -> Flask:
    return _create_app(TestConfig())


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000) # nosec
