"""Configuration for the game engine service."""

from __future__ import annotations

import os


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "GAME_ENGINE_DATABASE_URL", "sqlite:///game_engine.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False
    CATALOGUE_URL = os.getenv("CATALOGUE_URL", "http://catalogue:5000")
    CATALOGUE_REQUEST_TIMEOUT = float(os.getenv("CATALOGUE_REQUEST_TIMEOUT", "3"))
    CATALOGUE_USE_STUB_DATA = os.getenv("CATALOGUE_USE_STUB_DATA", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    CATALOGUE_USE_STUB_DATA = True
