"""Configuration for the Card Catalogue service."""
from __future__ import annotations

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
    JWT_COOKIE_SECURE = _bool_env("CATALOGUE_JWT_COOKIE_SECURE", True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_ALGORITHM = None
    JWT_SECRET_KEY = None

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "CATALOGUE_DATABASE_URL", "sqlite:///catalogue.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False

    def __init__(self):
        # init jwt keys or fallback secret
        self._init_keys()

    def _init_keys(self):
        # load a public key if available
        candidate_paths = [
            os.getenv("CATALOGUE_PUBLIC_KEY"),
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
            "CATALOGUE_JWT_SECRET", os.getenv("SECRET_KEY", "supersecretkey")
        )

class TestConfig:
    # JWT
    JWT_ALGORITHM = "HS256"
    JWT_SECRET_KEY = "test-secret"
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True
    
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
