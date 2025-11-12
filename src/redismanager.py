# redis extension for flask
from flask import current_app
from redis import Redis
import fakeredis

class RedisManager:
    def __init__(self, app=None):
        if app:
            self.init_app(app)

    def init_app(self, app):
        # whether we use the fake redis client or the real one
        use_fake = app.config.get("FAKE_REDIS", False)
        if use_fake:
            client = fakeredis.FakeRedis(decode_responses=True)
        else:
            redis_url = app.config.get("REDIS_URL", "redis://localhost:6379/0")
            client = Redis.from_url(redis_url, decode_responses=True)

        # register this client in the app's extensions
        if not hasattr(app, "extensions"):
            app.extensions = {}
        app.extensions["redis_manager"] = { "client": client }

        # setup a teardown handler to close redis at app's teardown
        def teardown_redis(_=None):
            try:
                client.close()
            except Exception:
                pass
        app.teardown_appcontext(teardown_redis)

    @property
    def conn(self):
        # retrieve current client from current_app's extensions
        ext = current_app.extensions.get("redis_manager")
        if not ext or "client" not in ext:
            raise RuntimeError("RedisManager not initialized for this app")
        return ext["client"]
