"""Application factory for the Card Catalogue microservice."""
from __future__ import annotations
from .config import Config, TestConfig
from .extensions import db
from .routes import catalogue as catalogue_blueprint
from flask import Flask

def _create_app(config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    app.register_blueprint(catalogue_blueprint)
    return app

def create_app() -> Flask:
    return _create_app(Config())

def create_test_app() -> Flask:
    return _create_app(TestConfig())

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5001)
