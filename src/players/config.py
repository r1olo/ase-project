"""Configuration for the players service."""

from __future__ import annotations

import os


class Config:
    # --- Database Configuration ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "PLAYERS_DATABASE_URL", "sqlite:///players.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    TESTING = False

    # --- JWT Configuration (Necessaria per flask-jwt-extended) ---
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    
    # Percorso della chiave pubblica
    _public_key_path = os.getenv("AUTH_PUBLIC_KEY_PATH", "jwtRS256.key.pub")

    # Logica per scegliere l'algoritmo
    if os.path.exists(_public_key_path):
        # PRODUZIONE/STAGING: Usiamo la chiave pubblica RSA
        with open(_public_key_path, "r") as f:
            JWT_PUBLIC_KEY = f.read()
        JWT_ALGORITHM = "RS256"
    else:
        # SVILUPPO LOCALE (Fallback): Se manca la chiave, usiamo HS256
        # Questo evita che l'app crashi se lanci i test senza il file della chiave
        JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "supersecretkey")
        JWT_ALGORITHM = "HS256"


class TestConfig(Config):
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    TESTING = True
    # Per i test, spesso è comodo disabilitare la verifica CSRF se presente, 
    # ma con i JWT puri non serve solitamente.