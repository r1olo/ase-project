# models/match.py
from typing import Dict, List, Optional, Any, Enum 
from sqlalchemy.orm import Mapped, mapped_column 
from extensions import db

from move import Move 

class MatchStatus(Enum):
    """
    Enumeration for the state of a match.
    """
    SETUP = "SETUP"
    DECK_SELECTION = "DECK_SELECTION"
    IN_PROGRESS = "IN_PROGRESS"
    FINISHED = "FINISHED"

class Match(db.Model):
    """
    Represents a match between two players.
    """
    __tablename__ = 'matches'

    id: Mapped[int] = mapped_column(db.Integer, primary_key=True)
    player1_id: Mapped[int] = mapped_column(db.Integer, nullable=False, index=True)
    player2_id: Mapped[int] = mapped_column(db.Integer, nullable=False, index=True)
    winner_id: Mapped[Optional[int]] = mapped_column(db.Integer, nullable=True)
    status: Mapped[MatchStatus] = mapped_column(
        db.Enum(MatchStatus), 
        nullable=False, 
        default=MatchStatus.SETUP
    )
    current_round: Mapped[int] = mapped_column(db.Integer, nullable=False, default=1)
    player1_deck: Mapped[Optional[List[Any]]] = mapped_column(db.JSON, nullable=True)
    player2_deck: Mapped[Optional[List[Any]]] = mapped_column(db.JSON, nullable=True)

    # Query object for related Move instances
    # The moves are fetched lazily and can be accessed via match.moves  
    moves: Mapped[List["Move"]] = db.relationship(
        'Move',
        back_populates='match',
        lazy='dynamic',
        cascade="all, delete-orphan"
    )

    def to_json(self, include_moves: bool = False) -> Dict[str, Any]:
        """
        Serializes the Match object to a dictionary for JSON responses.
        """
        payload = {
            "id": self.id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "winner_id": self.winner_id,
            "status": self.status.name,
            "current_round": self.current_round,
            "player1_deck": self.player1_deck,
            "player2_deck": self.player2_deck,
        }
        
        if include_moves:
            payload["moves"] = [move.to_json() for move in self.moves]

        return payload

    @classmethod
    def from_json(cls, json_data: Dict[str, Any]) -> "Match":
        """
        Creates a new Match instance from JSON payload.
        """
        player1_id = json_data.get('player1_id')
        player2_id = json_data.get('player2_id')

        if not player1_id or not player2_id:
            raise ValueError("player1_id and player2_id are required for creation.")

        return cls(player1_id=player1_id, player2_id=player2_id)

    def __repr__(self) -> str:
        return f'<Match {self.id} | {self.status.name} | P1:{self.player1_id} vs P2:{self.player2_id}>'