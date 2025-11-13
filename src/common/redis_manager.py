"""Reusable Redis manager for Flask apps."""

from __future__ import annotations

from flask import current_app
from redis import Redis
import fakeredis


class RedisManager:
    """Creates a Redis client per Flask app, supporting fakeredis for tests."""

    def __init__(self, extension_name: str = "redis_manager"):
        self._extension_name = extension_name

    def init_app(self, app):
        use_fake = app.config.get("FAKE_REDIS", False)
        if use_fake:
            client = fakeredis.FakeRedis(decode_responses=True)
        else:
            redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
            client = Redis.from_url(redis_url, decode_responses=True)

        app.extensions[self._extension_name] = {"client": client}

        @app.teardown_appcontext
        def teardown_redis(_=None):
            try:
                client.close()
            except Exception:
                pass

    @property
    def conn(self):
        ext = current_app.extensions.get(self._extension_name)
        if not ext or "client" not in ext:
            raise RuntimeError("RedisManager not initialized for this app")
        return ext["client"]
