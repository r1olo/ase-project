from common.extensions import db
from typing import Dict, List, Optional, Any, Enum 
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, DateTime, JSON
from datetime import datetime, UTC


from move import Move 

def utcnow() -> datetime:
    """Returns the current UTC time."""
    return datetime.now(UTC)

class MatchStatus(Enum):
    """Enumeration for the state of a match."""
    SETUP = "SETUP"                 # Match created, waiting for deck selection
    DECK_SELECTION = "DECK_SELECTION" # Players are choosing their card subsets
    IN_PROGRESS = "IN_PROGRESS"     # Game is actively being played
    FINISHED = "FINISHED"             # Game has a winner and is over


class Match(db.Model):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # Player IDs from your user service
    player1_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    player2_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # Game state
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus), nullable=False, default=MatchStatus.SETUP
    )
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    # Deck data
    player1_deck: Mapped[Optional[Dict[str, Any] | List[Any]]] = mapped_column(
        JSON, nullable=True
    )
    player2_deck: Mapped[Optional[Dict[str, Any] | List[Any]]] = mapped_column(
        JSON, nullable=True
    )
    
    winner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # Relationship
    # Note: lazy="dynamic" was removed to match your style.
    # self.moves will be a list, not a query.
    moves: Mapped[list["Move"]] = relationship(
        "Move", back_populates="match", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        player1_id: int,
        player2_id: int,
        status: MatchStatus = MatchStatus.SETUP,
        current_round: int = 1,
        player1_deck: Optional[Dict | List] = None,
        player2_deck: Optional[Dict | List] = None,
        winner_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.status = status
        self.current_round = current_round
        self.player1_deck = player1_deck
        self.player2_deck = player2_deck
        self.winner_id = winner_id
        now = utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self, include_moves: bool = False) -> dict:
        """
        Serializes the Match object to a dictionary.
        """
        payload = {
            "id": self.id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "status": self.status.name,
            "current_round": self.current_round,
            "player1_deck": self.player1_deck,
            "player2_deck": self.player2_deck,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

        # Only add the 'moves' key if the flag is True
        if include_moves:
            payload["moves"] = [m.to_dict() for m in self.moves]
        
        return payload