"""Database models for the catalogue service."""

from __future__ import annotations

from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column

from .extensions import db


class Card(db.Model):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    image: Mapped[str] = mapped_column(String(255), nullable=False)
    economy: Mapped[int] = mapped_column(Integer, nullable=False)
    food: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[int] = mapped_column(Integer, nullable=False)
    special: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[float] = mapped_column(Float, nullable=False)

    def __init__(
        self,
        name: str,
        image: str,
        economy: int,
        food: int,
        environment: int,
        special: int,
        total: float,
    ):
        self.name = name
        self.image = image
        self.economy = economy
        self.food = food
        self.environment = environment
        self.special = special
        self.total = total

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "economy": self.economy,
            "food": self.food,
            "environment": self.environment,
            "special": self.special,
            "total": self.total,
        }
