"""Minimal API gateway app."""

from __future__ import annotations

from flask import Flask

from .config import Config
from .routes import bp as gateway_blueprint


def create_app(config_object=Config()) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    app.register_blueprint(gateway_blueprint)
    return app


if __name__ == "__main__":  # pragma: no cover
    create_app().run(host="0.0.0.0", port=80)
