from random import choice
from common.extensions import db
from typing import Dict, Optional, Any
from enum import Enum as PyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, DateTime, JSON, String, ForeignKey, UniqueConstraint, Enum as SAEnum
from datetime import datetime, UTC

# --- Constants ---

# The categories of stats cards are compared on.
CARD_CATEGORIES = ["economy", "food", "environment", "special", "total"]

# --- Helper Functions ---

def utcnow():
    """Returns the current datetime in UTC."""
    return datetime.now(UTC)

# --- Model Definitions ---

class MatchStatus(PyEnum):
    """Enumeration for the state of a match."""
    SETUP = "SETUP"                 # Waiting for players to choose decks
    IN_PROGRESS = "IN_PROGRESS"     # Game is actively being played
    FINISHED = "FINISHED"           # Game is over


class Match(db.Model):
    """
    Represents the high-level state of a single card game, including
    players, scores, and deck information.
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
        SAEnum(MatchStatus), nullable=False, default=MatchStatus.SETUP
    )

    # --- Player Deck Storage ---
    # Stores the full stats map for the deck
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
    rounds: Mapped[list["Round"]] = relationship(
        "Round", back_populates="match", cascade="all, delete-orphan", order_by="Round.round_number"
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
        
        self.player1_score = 0
        self.player2_score = 0
        
        now = utcnow()
        self.created_at = kwargs.get("created_at", now)
        self.updated_at = kwargs.get("updated_at", now)

    def to_dict(self, include_rounds: bool = False) -> dict:
        """
        Serializes the Match object to a dictionary.
        
        :param include_rounds: If True, includes the full list of rounds.
                               Defaults to False to avoid N+1 queries.
        """
        payload = {
            "id": self.id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "status": self.status.name,
            "player1_score": self.player1_score,
            "player2_score": self.player2_score,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # Note: We don't return the full deck stats by default
        }

        if include_rounds:
            payload["rounds"] = [r.to_dict() for r in self.rounds]
        
        return payload


class Round(db.Model):
    """
    Represents a single round of play between two players.
    Contains both player moves and the round outcome.
    """
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("matches.id"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    
    # The category used to compare cards this round
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    
    # Cards played by each player (stores card IDs like "card_name_001")
    player1_card_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    player2_card_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    
    # Winner of this round (null if draw or not yet complete)
    winner_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    # --- Relationships ---
    match: Mapped["Match"] = relationship("Match", back_populates="rounds")

    # --- Constraints ---
    # Ensure only one round per round_number per match
    __table_args__ = (
        UniqueConstraint(
            'match_id', 
            'round_number', 
            name='_match_round_number_uc'
        ),
    )

    def __init__(
        self,
        round_number: int,
        category: str,
        match: Optional[Match] = None,
        match_id: Optional[int] = None,
        player1_card_id: Optional[str] = None,
        player2_card_id: Optional[str] = None,
        winner_id: Optional[int] = None,
        **kwargs
    ):
        if match is not None:
            self.match = match
        if match_id is not None:
            self.match_id = match_id
            
        self.round_number = round_number
        self.category = category
        self.player1_card_id = player1_card_id
        self.player2_card_id = player2_card_id
        self.winner_id = winner_id
        
        now = utcnow()
        self.created_at = kwargs.get("created_at", now)
        self.updated_at = kwargs.get("updated_at", now)

    def is_complete(self) -> bool:
        """Check if both players have submitted their cards."""
        return self.player1_card_id is not None and self.player2_card_id is not None

    def to_dict(self) -> dict:
        """Serializes the Round object to a dictionary."""
        return {
            "id": self.id,
            "match_id": self.match_id,
            "round_number": self.round_number,
            "category": self.category,
            "player1_card_id": self.player1_card_id,
            "player2_card_id": self.player2_card_id,
            "winner_id": self.winner_id,
            "is_complete": self.is_complete(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
