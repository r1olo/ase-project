# configuration for auth microservice
import os
from datetime import timedelta

# extract a boolean value out of an env variable
def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}

class Config:
    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = os.getenv("AUTH_DATABASE_URL",
                                        "sqlite:///:memory:")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # JWT token stuff
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_COOKIE_SECURE = _bool_env("AUTH_JWT_COOKIE_SECURE", True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_ALGORITHM = None
    JWT_SECRET_KEY = None

    # Redis
    FAKE_REDIS = False
    REDIS_URL = os.getenv("AUTH_REDIS_URL", "redis://auth-redis:6379/0")

    # testing
    TESTING = False

    def __init__(self):
        # init keys
        self._init_keys()

    def _init_keys(self):
        # init keys for the normal configuration
        priv_path = os.getenv("AUTH_PRIVATE_KEY")
        pub_path = os.getenv("AUTH_PUBLIC_KEY")

        # if paths are set and valid, read the files
        if priv_path and pub_path and os.path.exists(priv_path) and os.path.exists(pub_path):
            with open(priv_path, "r") as f:
                self.JWT_PRIVATE_KEY = f.read()
            with open(pub_path, "r") as f:
                self.JWT_PUBLIC_KEY = f.read()
            self.JWT_ALGORITHM = "RS256"
            return

        # try default files
        if os.path.exists("jwtRS256.key") and os.path.exists("jwtRS256.key.pub"):
            with open("jwtRS256.key") as f:
                self.JWT_PRIVATE_KEY = f.read()
            with open("jwtRS256.key.pub") as f:
                self.JWT_PUBLIC_KEY = f.read()
            self.JWT_ALGORITHM = "RS256"
            return

        # fallback to symmetric encryption
        self.JWT_ALGORITHM = "HS256"
        self.JWT_SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")

class TestConfig(Config):
    # SQLAlchemy
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    # JWT
    JWT_SECRET_KEY = "test-secret"
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True

    # Redis
    FAKE_REDIS = True

    # testing
    TESTING = True
