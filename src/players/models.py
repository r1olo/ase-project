"""Database models for the players service."""

from __future__ import annotations
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from common.extensions import db

class Player(db.Model):
    __tablename__ = "players"
    
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=True)

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
    player1_id: Mapped[int] = mapped_column(Integer, foreign_key="players.id", index=True, nullable=False)
    player2_id: Mapped[int] = mapped_column(Integer, foreign_key="players.id", index=True, nullable=False)
    accepted: Mapped[str] = mapped_column(Boolean, nullable=False)

    def __init__(self,
        player1_id: int,
        player2_id: int,
        accepted: bool = False
    ):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.accepted = accepted

    def to_dict(self) -> dict:
        return {
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "status": "accepted" if self.accepted else "pending",
        }
