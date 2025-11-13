"""Configuration for the API gateway."""

from __future__ import annotations

import os


class Config:
    SERVICE_DEFAULTS = {
        "auth": os.getenv("GATEWAY_AUTH_URL", "http://auth:5000"),
        "players": os.getenv("GATEWAY_PLAYERS_URL", "http://players:5000"),
        "catalogue": os.getenv("GATEWAY_CATALOGUE_URL", "http://catalogue:5000"),
        "matchmaking": os.getenv("GATEWAY_MATCHMAKING_URL", "http://matchmaking:5000"),
        "game_engine": os.getenv("GATEWAY_GAME_ENGINE_URL", "http://game-engine:5000"),
    }
    REQUEST_TIMEOUT = float(os.getenv("GATEWAY_REQUEST_TIMEOUT", "2.0"))
    TESTING = False


class TestConfig(Config):
    TESTING = True
