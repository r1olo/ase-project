"""Database models for the players service."""

from __future__ import annotations
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from common.extensions import db


class Player(db.Model):
    __tablename__ = "players"
    
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String(20), nullable=True)
    
    def __init__(
        self,
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