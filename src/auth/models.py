"""Database models for the auth microservice."""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


def utcnow():
    return datetime.now(UTC)


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    pw_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    def __init__(
        self,
        email: str,
        pw_hash: str,
        created_at: datetime | None = None,
    ):
        self.email = email
        self.pw_hash = pw_hash
        self.created_at = created_at or utcnow()

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email}>"
