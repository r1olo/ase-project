# Card representation
from sqlalchemy import Integer, Float, String
from sqlalchemy.orm import Mapped, mapped_column
from ..extensions import db

class Card(db.Model):
    __tablename__ = 'cards'
    id : Mapped[int] = mapped_column(Integer, primary_key=True)
    name : Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    image : Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    economy_pts : Mapped[int] = mapped_column(Integer, nullable=False)
    food_pts : Mapped[int] = mapped_column(Integer, nullable=False)
    environment_pts : Mapped[int] = mapped_column(Integer, nullable=False)
    special_pts : Mapped[int] = mapped_column(Integer, nullable=False)
    total_pts : Mapped[float] = mapped_column(Float, nullable=False)

    def __init__(self, name: str, image: str, economy: int, food: int, environment: int, special: int, total: float):
        self.name = name
        self.image = image
        self.economy_pts = economy
        self.food_pts = food
        self.environment_pts = environment
        self.special_pts = special
        self.total_pts = total

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "image": self.image,
            "economy": self.economy_pts,
            "food": self.food_pts,
            "environment": self.environment_pts,
            "special": self.special_pts,
            "total": self.total_pts
        }
