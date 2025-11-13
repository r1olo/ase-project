"""Configuration objects for the auth microservice."""

from __future__ import annotations

import os
from datetime import timedelta


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


class Config:
    """Production-ish defaults that can be overridden via env vars."""

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "AUTH_DATABASE_URL",
        "sqlite:///auth.db",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.getenv("AUTH_JWT_SECRET", "change-me")
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_SECURE = _bool_env("AUTH_JWT_COOKIE_SECURE", True)
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("AUTH_ACCESS_EXPIRES_MIN", "15"))
    )
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("AUTH_REFRESH_EXPIRES_DAYS", "30"))
    )

    FAKE_REDIS = _bool_env("AUTH_FAKE_REDIS", False)
    REDIS_URL = os.getenv("AUTH_REDIS_URL", "redis://auth-redis:6379/0")

    TESTING = False


class TestConfig(Config):
    """Lightweight configuration for unit tests."""

    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_SECRET_KEY = "test-secret"
    JWT_COOKIE_SECURE = False
    JWT_COOKIE_CSRF_PROTECT = True
    FAKE_REDIS = True
    TESTING = True
