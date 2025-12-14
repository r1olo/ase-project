# configuration for matchmaking microservice
import os

# convert env var into boolean
def _bool_env(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}

class Config:
    # JWT
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_COOKIE_SECURE = _bool_env("MATCHMAKING_JWT_COOKIE_SECURE", True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_ALGORITHM = None
    JWT_SECRET_KEY = None

    # Redis
    FAKE_REDIS = False
    REDIS_URL = os.getenv("MATCHMAKING_REDIS_URL", "redis://matchmaking-redis:6379/0")

    # variable stuff
    MATCHMAKING_QUEUE_KEY = os.getenv("MATCHMAKING_QUEUE_KEY", "matchmaking:queue")
    MATCHMAKING_STATUS_KEY = os.getenv("MATCHMAKING_STATUS_KEY", f"{MATCHMAKING_QUEUE_KEY}:status")
    MATCHMAKING_MAX_QUEUE_SIZE = int(os.getenv("MATCHMAKING_MAX_QUEUE_SIZE", "500"))
    GAME_ENGINE_URL = os.getenv("GAME_ENGINE_URL", "https://game-engine:5000")
    GAME_ENGINE_REQUEST_TIMEOUT = float(os.getenv("GAME_ENGINE_REQUEST_TIMEOUT", "3"))

    # testing
    TESTING = False

    def __init__(self):
        # init jwt keys or fallback secret
        self._init_keys()

    def _init_keys(self):
        # load a public key if available
        candidate_paths = [
            os.getenv("MATCHMAKING_PUBLIC_KEY"),
            os.getenv("AUTH_PUBLIC_KEY"),
            "jwtRS256.key.pub",
        ]
        for path in candidate_paths:
            if path and os.path.exists(path):
                with open(path) as f:
                    self.JWT_PUBLIC_KEY = f.read()
                self.JWT_ALGORITHM = "RS256"
                return

        # fallback to symmetric encryption
        self.JWT_ALGORITHM = "HS256"
        self.JWT_SECRET_KEY = os.getenv(
            "MATCHMAKING_JWT_SECRET", os.getenv("SECRET_KEY", "supersecretkey")
        )

class TestConfig(Config):
    # JWT
    JWT_SECRET_KEY = "test-secret" # nosec
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True

    # Redis
    FAKE_REDIS = True

    # testing
    TESTING = True
