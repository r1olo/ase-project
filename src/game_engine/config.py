"""Configuration for the game engine service."""
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
    JWT_COOKIE_SECURE = _bool_env("GAME_ENGINE_JWT_COOKIE_SECURE", True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_ALGORITHM = None
    JWT_SECRET_KEY = None

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "GAME_ENGINE_DATABASE_URL", "sqlite:///game_engine.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False
    CATALOGUE_URL = os.getenv("CATALOGUE_URL", "http://catalogue:5000")
    CATALOGUE_REQUEST_TIMEOUT = float(os.getenv("CATALOGUE_REQUEST_TIMEOUT", "3"))

    def __init__(self):
        # init jwt keys or fallback secret
        self._init_keys()

    def _init_keys(self):
        # load a public key if available
        candidate_paths = [
            os.getenv("GAME_ENGINE_PUBLIC_KEY"),
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
            "GAME_ENGINE_JWT_SECRET", os.getenv("SECRET_KEY", "supersecretkey")
        )

class TestConfig(Config):
    # JWT
    JWT_SECRET_KEY = "test-secret"
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True

    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True