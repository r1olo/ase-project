# reusable Redis client for Flask
from flask import current_app
from redis import Redis
import fakeredis

class RedisManager:
    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        # pick either the fake redis or the real one
        use_fake = app.config.get("FAKE_REDIS", False)
        if use_fake:
            client = fakeredis.FakeRedis(decode_responses=True)
        else:
            redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
            client = Redis.from_url(redis_url, decode_responses=True)

        # register the client in the current app's context
        app.extensions["redis-manager"] = {"client": client}

        # register teardown handler to close redis client
        def teardown_redis(_=None):
            try:
                client.close()
            except Exception:
                pass
        app.teardown_appcontext(teardown_redis)

    @property
    def conn(self):
        # retrieve the Redis client
        ext = current_app.extensions.get("redis-manager")
        if not ext or "client" not in ext:
            raise RuntimeError("RedisManager not initialized for this app")
        return ext["client"]
