# manage config through env vars
import os
from datetime import timedelta

# TODO
class Config:
    # database
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///:memory:")

    # token algorithm
    JWT_ALGORITHM = "RS256"
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_SECRET_KEY = None

    # token options
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)

    # redis
    FAKE_REDIS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    def __init__(self):
        # init keys
        self._init_keys()

    def _init_keys(self):
        # init keys for the normal configuration
        priv_path = os.getenv("PRIVATE_KEY")
        pub_path = os.getenv("PUBLIC_KEY")

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

# TODO find a better way
class TestConfig(Config):
    # database
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    # token algorithm
    JWT_SECRET_KEY = "test123"
    JWT_ALGORITHM = "HS256"

    # token options
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True

    # redis
    FAKE_REDIS = True

    def __init__(self):
        pass
