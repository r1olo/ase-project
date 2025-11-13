"""Flask extension singletons for the auth service."""

from __future__ import annotations

from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from redis import Redis
import fakeredis

from flask import current_app


bcrypt = Bcrypt()
db = SQLAlchemy()
jwt = JWTManager()


class RedisManager:
    """Very small helper to lazily provide a Redis client per Flask app."""

    def __init__(self):
        self._attr_name = "redis_manager"

    def init_app(self, app):
        use_fake = app.config.get("FAKE_REDIS", False)
        if use_fake:
            client = fakeredis.FakeRedis(decode_responses=True)
        else:
            redis_url = app.config.get("REDIS_URL")
            client = Redis.from_url(redis_url, decode_responses=True)

        app.extensions[self._attr_name] = {"client": client}

        @app.teardown_appcontext
        def close_redis(_=None):
            try:
                client.close()
            except Exception:
                pass

    @property
    def conn(self):
        ext = current_app.extensions.get(self._attr_name)
        if not ext:
            raise RuntimeError("RedisManager not initialized for this app")
        return ext["client"]


redis_manager = RedisManager()
