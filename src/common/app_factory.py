"""Shared Flask application factory helper."""

from __future__ import annotations

from collections.abc import Iterable, Callable
from typing import Protocol, Any

from flask import Flask


class Extension(Protocol):
    def init_app(self, app: Flask) -> Any: ...


def create_flask_app(
    *,
    config_obj,
    extensions: Iterable[Extension] = (),
    blueprints: Iterable = (),
    init_app_context_steps: Iterable[Callable[[Flask], Any]] = (),
) -> Flask:
    """Create a Flask app using shared configuration/extension wiring."""

    app = Flask(__name__)
    app.config.from_object(config_obj)

    for ext in extensions:
        ext.init_app(app)

    with app.app_context():
        for step in init_app_context_steps:
            step(app)

    for bp in blueprints:
        app.register_blueprint(bp)

    return app
