"""Database models for the players service."""

from __future__ import annotations
from datetime import datetime, UTC
from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from common.extensions import db


def utcnow():
    return datetime.now(UTC)


class Player(db.Model):
    __tablename__ = "players"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    #display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_picture: Mapped[str] = mapped_column(String(255), nullable=True)
    region: Mapped[str] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    def __init__(
        self,
        user_id: int,
        username: str,
        #display_name: str,
        profile_picture: str | None = None,
        region: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.user_id = user_id
        self.username = username
        #self.display_name = display_name
        self.profile_picture = profile_picture
        self.region = region
        now = utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            #"display_name": self.display_name,
            "profile_picture": self.profile_picture,
            "region": self.region,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
