"""Game engine database models."""

from __future__ import annotations

from datetime import datetime, UTC

from sqlalchemy import Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db


def utcnow():
    return datetime.now(UTC)


class Match(db.Model):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    metadata: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    rounds: Mapped[list["Round"]] = relationship(
        "Round", back_populates="match", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        public_id: str,
        status: str = "pending",
        metadata: str | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        self.public_id = public_id
        self.status = status
        self.metadata = metadata
        now = utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "public_id": self.public_id,
            "status": self.status,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "rounds": [r.to_dict() for r in self.rounds],
        }


class Round(db.Model):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(Integer, ForeignKey("matches.id"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    match: Mapped[Match] = relationship("Match", back_populates="rounds")

    def __init__(
        self,
        match: Match | None = None,
        match_id: int | None = None,
        round_number: int = 1,
        state: str | None = None,
        outcome: str | None = None,
        created_at: datetime | None = None,
    ):
        if match is not None:
            self.match = match
        if match_id is not None:
            self.match_id = match_id
        self.round_number = round_number
        self.state = state
        self.outcome = outcome
        self.created_at = created_at or utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "round_number": self.round_number,
            "state": self.state,
            "outcome": self.outcome,
            "created_at": self.created_at.isoformat(),
        }
