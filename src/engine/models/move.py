# models/move.py
import datetime
from typing import Any, Any, Dict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import ForeignKey, UniqueConstraint  # <-- Import constraints
from extensions import db

from match import Match

class Move(db.Model):
    """
    Represents a single move (one card played) by one player 
    in one round of a match.
    """
    __tablename__ = 'moves'
    
    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        ForeignKey('matches.id'), 
        nullable=False, 
        index=True
    )
    player_id: Mapped[int] = mapped_column(db.Integer, nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(db.Integer, nullable=False, index=True)
    card_id: Mapped[str] = mapped_column(db.String(100), nullable=False) 
    created_at: Mapped[datetime.datetime] = mapped_column(
        db.DateTime, 
        nullable=False, 
        default=datetime.datetime.utcnow
    )
    
    # Links this Move back to its parent Match object
    match: Mapped["Match"] = db.relationship('Match', back_populates='moves')

    __table_args__ = (
        UniqueConstraint(
            'match_id', 
            'player_id', 
            'round_number', 
            name='_match_player_round_uc'
        ),
    )

    def to_json(self) -> Dict[str, Any]:
        """
        Serializes the Move object to a dictionary for JSON responses.
        """
        return {
            "id": self.id,
            "match_id": self.match_id,
            "player_id": self.player_id,
            "round_number": self.round_number,
            "card_id": self.card_id,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> "Move":
        """
        Creates a new Move instance from a JSON payload.
        """
        required_fields = ['match_id', 'player_id', 'round_number', 'card_id']
        
        if not all(field in json_data for field in required_fields):
            raise ValueError(f"Missing one of required fields: {required_fields}")

        return cls(
            match_id=json_data.get('match_id'),
            player_id=json_data.get('player_id'),
            round_number=json_data.get('round_number'),
            card_id=json_data.get('card_id')
        )

    def __repr__(self) -> str:
        return (f'<Move {self.id} | Match:{self.match_id} R:{self.round_number} '
                f'P:{self.player_id} Card:{self.card_id}>')