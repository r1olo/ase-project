"""Database models for the players service."""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


def utcnow():
    return datetime.now(UTC)


class PlayerProfile(db.Model):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    #user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    #display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_picture: Mapped[str] = mapped_column(String(255), nullable=True)
    nation: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    def __init__(
        self,
        username: str,
        #user_id: int,
        #display_name: str,
        profile_picture: str | None = None,
        nation: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.username = username
        #self.user_id = user_id
        #self.display_name = display_name
        self.profile_picture = profile_picture
        self.nation = nation
        now = utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> dict:
        return {
            "username": self.username,
            #"user_id": self.user_id,
            #"display_name": self.display_name,
            "profile_picture": self.profile_picture,
            "nation": self.nation,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
