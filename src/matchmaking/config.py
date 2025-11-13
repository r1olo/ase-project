"""Configuration for the matchmaking service."""

from __future__ import annotations

import os


class Config:
    MAX_QUEUE_SIZE = int(os.getenv("MATCHMAKING_MAX_QUEUE_SIZE", "500"))
    TESTING = False


class TestConfig(Config):
    TESTING = True
