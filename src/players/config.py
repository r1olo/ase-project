"""Configuration for the players service."""

from __future__ import annotations

import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "PLAYERS_DATABASE_URL", "sqlite:///players.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
