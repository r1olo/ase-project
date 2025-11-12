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
    
    @classmethod
    def from_json(cls, data: dict):        
        name = data.get("name")
        image = data.get("image")
        economy = data.get("economy")
        food = data.get("food")
        environment = data.get("environment")
        special = data.get("special")
        total = data.get("total")

        error_msg = "Invalid or missing {} field to create Card"
        if not (isinstance(name, str) and name.strip()):
            raise ValueError(error_msg.format("name"))
        if not (isinstance(image, str) and image.strip()):
            raise ValueError(error_msg.format("image"))
        if not isinstance(economy, int):
            raise ValueError(error_msg.format("economy"))
        if not isinstance(food, int):
            raise ValueError(error_msg.format("food"))
        if not isinstance(environment, int):
            raise ValueError(error_msg.format("environment"))
        if not isinstance(special, int):
            raise ValueError(error_msg.format("special"))
        if not isinstance(total, float):
            raise ValueError(error_msg.format("total"))

        return cls(
            name=name,
            image=image,
            economy=economy,
            food=food,
            environment=environment,
            special=special,
            total=total
        )
