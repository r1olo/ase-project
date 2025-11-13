from common.extensions import db
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, UniqueConstraint, Integer, String, DateTime  

from match import Match

def utcnow() -> datetime:
    """Returns the current UTC time."""
    return datetime.now(datetime.UTC)

class Move(db.Model):
    """
    Represents a single card played by a single player in one round.
    This is an append-only log of game actions.
    """
    __tablename__ = "moves"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id"), nullable=False, index=True
    )
    player_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Stores the card ID (e.g., "card_name_001")
    card_id: Mapped[str] = mapped_column(String(100), nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )

    # --- Relationships ---
    # A Move belongs to one Match.
    match: Mapped["Match"] = relationship("Match", back_populates="moves")

    # --- Constraints ---
    # This is a critical game rule: A player can only submit ONE
    # move per round in a given match.
    __table_args__ = (
        UniqueConstraint(
            'match_id', 
            'player_id', 
            'round_number', 
            name='_match_player_round_uc'
        ),
    )

    def __init__(
        self,
        player_id: int,
        round_number: int,
        card_id: str,
        match: Optional[Match] = None,
        match_id: Optional[int] = None,
        **kwargs
    ):
        if match is not None:
            self.match = match
        if match_id is not None:
            self.match_id = match_id
            
        self.player_id = player_id
        self.round_number = round_number
        self.card_id = card_id
        self.created_at = kwargs.get("created_at", utcnow())

    def to_dict(self) -> dict:
        """Serializes the Move object to a dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "player_id": self.player_id,
            "round_number": self.round_number,
            "card_id": self.card_id,
            "created_at": self.created_at.isoformat(),
        }