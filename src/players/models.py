"""Database models for the players service."""

from __future__ import annotations
from enum import StrEnum
from sqlalchemy import Boolean, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from common.extensions import db

# Definisci l'Enum con le regioni permesse
class Region(StrEnum):
    ABRUZZO = "Abruzzo"
    BASILICATA = "Basilicata"
    CALABRIA = "Calabria"
    CAMPANIA = "Campania"
    EMILIA_ROMAGNA = "Emilia-Romagna"
    FRIULI_VENEZIA_GIULIA = "Friuli-Venezia Giulia"
    LAZIO = "Lazio"
    LIGURIA = "Liguria"
    LOMBARDIA = "Lombardia"
    MARCHE = "Marche"
    MOLISE = "Molise"
    PIEMONTE = "Piemonte"
    PUGLIA = "Puglia"
    SARDEGNA = "Sardegna"
    SICILIA = "Sicilia"
    TOSCANA = "Toscana"
    TRENTINO_ALTO_ADIGE = "Trentino-Alto Adige"
    UMBRIA = "Umbria"
    VALLE_D_AOSTA = "Valle d'Aosta"
    VENETO = "Veneto"

class Player(db.Model):
    __tablename__ = "players"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String(25), nullable=True)

    def __init__(self,
        user_id: int,
        username: str,
        region: str | None = None,
    ):
        self.user_id = user_id
        self.username = username
        self.region = region

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "region": self.region,
        }
    
class Friendship(db.Model):
    __tablename__ = "friends"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    player1_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    player2_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), index=True, nullable=False)
    requester_id: Mapped[int] = mapped_column(Integer, ForeignKey("players.id"), nullable=False)
    
    accepted: Mapped[str] = mapped_column(Boolean, nullable=False)

    def __init__(self,
        player1_id: int,
        player2_id: int,
        requester_id: int,
        accepted: bool = False
    ):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.requester_id = requester_id
        self.accepted = accepted

    def to_dict(self) -> dict:
        return {
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "requester_id": self.requester_id,
            "status": "accepted" if self.accepted else "pending",
        }
