# User representation
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from ..extensions import db

class User(db.Model):
    __tablename__ = "users"
    id : Mapped[int] = mapped_column(Integer, primary_key=True)
    user : Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email : Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    pw_hash : Mapped[str] = mapped_column(String(128), nullable=False)

    def __init__(self, user: str, email: str, pw_hash: str):
        self.user = user
        self.email = email
        self.pw_hash = pw_hash
