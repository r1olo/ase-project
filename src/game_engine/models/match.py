from random import random
from common.extensions import db
from typing import Dict, Optional, Any, Enum 
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, DateTime, JSON, String
from datetime import datetime, UTC

from move import Move 

# --- Constants ---

# The categories of stats cards are compared on.
CARD_CATEGORIES = ["economy", "food", "environment", "special", "total"]

# --- Helper Functions ---

def utcnow():
    """Returns the current datetime in UTC."""
    return datetime.now(UTC)

# --- Model Definitions ---

class MatchStatus(Enum):
    """Enumeration for the state of a match."""
    SETUP = "SETUP"                 # Waiting for players to choose decks
    IN_PROGRESS = "IN_PROGRESS"     # Game is actively being played
    FINISHED = "FINISHED"           # Game is over

class Match(db.Model):
    """
    Represents the high-level state of a single card game, including
    players, scores, and current round state.
    """
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    
    # --- Player and Score Tracking ---
    player1_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    player2_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    player1_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    player2_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    winner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Game State ---
    status: Mapped[MatchStatus] = mapped_column(
        Enum(MatchStatus), nullable=False, default=MatchStatus.SETUP
    )
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    
    current_round_category: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # --- Player Deck Storage ---
    # Stores the full stats map for the deck,
    player1_deck: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    player2_deck: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # --- Relationships ---
    moves: Mapped[list["Move"]] = relationship(
        "Move", back_populates="match", cascade="all, delete-orphan"
    )

    def __init__(
        self,
        player1_id: int,
        player2_id: int,
        status: MatchStatus = MatchStatus.SETUP,
        **kwargs
    ):
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.status = status

        self.current_round = 1
        self.player1_score = 0
        self.player2_score = 0
        
        self.current_round_category = random.choice(CARD_CATEGORIES)
        
        now = utcnow()
        self.created_at = kwargs.get("created_at", now)
        self.updated_at = kwargs.get("updated_at", now)

    def to_dict(self, include_moves: bool = False) -> dict:
        """
        Serializes the Match object to a dictionary.
        
        :param include_moves: If True, includes the full list of moves.
                              Defaults to False to avoid N+1 queries.
        """
        payload = {
            "id": self.id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "status": self.status.name,
            "current_round": self.current_round,
            "player1_score": self.player1_score,
            "player2_score": self.player2_score,
            "current_round_category": self.current_round_category,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Note: We don't return the full deck stats by default
        }

        if include_moves:
            payload["moves"] = [m.to_dict() for m in self.moves]
        
        return payload