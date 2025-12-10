"""
Mock data and helpers for testing without DB and external services.
"""
import json
import os
from typing import Dict, List, Optional
from datetime import datetime
from .models import Match, Round, MatchStatus

# In-memory storage for testing
MOCK_MATCHES = {}
MOCK_ROUNDS = {}
MOCK_MATCH_COUNTER = 1
MOCK_ROUND_COUNTER = 1
MOCK_CARD_CATALOGUE = {}

def _load_mock_cards():
    """
    Loads cards from cards/cards.json into the MOCK_CARD_CATALOGUE.
    Mimics the logic from the app factory where IDs are assigned by index.
    """
    global MOCK_CARD_CATALOGUE
    
    # Try to find the file. We look in the current directory or one level up
    # depending on where the test runner is executed from.
    file_path = "cards/cards.json"
    if not os.path.exists(file_path):
        # Fallback for when running from a different root (e.g. inside tests/)
        file_path = "../cards/cards.json"
        
    try:
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                cards_list = json.load(f)
                
                for idx, card in enumerate(cards_list):
                    # Assign ID based on index + 1 (matching your app factory logic)
                    card_id = idx + 1
                    card["id"] = card_id
                    MOCK_CARD_CATALOGUE[card_id] = card
        else:
            print(f"Warning: Mock data could not find {file_path}. Catalogue is empty.")
    except Exception as e:
        print(f"Error loading mock cards: {e}")

# Load cards immediately upon module import
_load_mock_cards()


def reset_mock_data():
    """Reset all mock data - useful between tests."""
    global MOCK_MATCHES, MOCK_ROUNDS, MOCK_MATCH_COUNTER, MOCK_ROUND_COUNTER
    MOCK_MATCHES = {}
    MOCK_ROUNDS = {}
    MOCK_MATCH_COUNTER = 1
    MOCK_ROUND_COUNTER = 1
    # We generally don't need to reload cards, as they are static data, 
    # but if tests modify card data, uncomment the line below:
    # _load_mock_cards()


def get_next_match_id() -> int:
    """Generate next match ID."""
    global MOCK_MATCH_COUNTER
    id_val = MOCK_MATCH_COUNTER
    MOCK_MATCH_COUNTER += 1
    return id_val


def get_next_round_id() -> int:
    """Generate next round ID."""
    global MOCK_ROUND_COUNTER
    id_val = MOCK_ROUND_COUNTER
    MOCK_ROUND_COUNTER += 1
    return id_val


class MockMatch:
    """Mock Match object that mimics SQLAlchemy model."""
    
    def __init__(self, id: int, player1_id: int, player2_id: int):
        self.id = id
        self.player1_id = player1_id
        self.player2_id = player2_id
        self.player1_deck = None
        self.player2_deck = None
        self.player1_score = 0
        self.player2_score = 0
        self.status = MatchStatus.PENDING
        self.winner_id = None
        self.created_at = datetime.utcnow()
        self.rounds = []
    
    def to_dict(self, include_rounds: bool = False):
        result = {
            "id": self.id,
            "player1_id": self.player1_id,
            "player2_id": self.player2_id,
            "player1_score": self.player1_score,
            "player2_score": self.player2_score,
            "status": self.status.value,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_rounds:
            result["rounds"] = [r.to_dict() for r in self.rounds]
        return result


class MockRound:
    """Mock Round object that mimics SQLAlchemy model."""
    
    def __init__(self, id: int, match_id: int, round_number: int, category: str):
        self.id = id
        self.match_id = match_id
        self.round_number = round_number
        self.category = category
        self.player1_card_id = None
        self.player2_card_id = None
        self.winner_id = None
        self.created_at = datetime.utcnow()
    
    def to_dict(self):
        return {
            "id": self.id,
            "match_id": self.match_id,
            "round_number": self.round_number,
            "category": self.category,
            "player1_card_id": self.player1_card_id,
            "player2_card_id": self.player2_card_id,
            "winner_id": self.winner_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MockMatchRepository:
    """Mock repository for match operations."""
    
    def create(self, player1_id: int, player2_id: int) -> MockMatch:
        match_id = get_next_match_id()
        match = MockMatch(match_id, player1_id, player2_id)
        MOCK_MATCHES[match_id] = match
        return match
    
    def find_by_id(self, match_id: int) -> Optional[MockMatch]:
        return MOCK_MATCHES.get(match_id)
    
    def find_by_id_with_lock(self, match_id: int) -> Optional[MockMatch]:
        # In mock mode, no actual locking needed
        return MOCK_MATCHES.get(match_id)
    
    def find_by_id_with_rounds(self, match_id: int) -> Optional[MockMatch]:
        match = MOCK_MATCHES.get(match_id)
        if match:
            # Attach rounds
            match.rounds = [r for r in MOCK_ROUNDS.values() if r.match_id == match_id]
            match.rounds.sort(key=lambda r: r.round_number)
        return match
    
    def find_for_player(
        self,
        player_id: int,
        status: Optional[MatchStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> List[MockMatch]:
        matches = [
            m for m in MOCK_MATCHES.values()
            if (m.player1_id == player_id or m.player2_id == player_id)
            and (status is None or m.status == status)
        ]
        # Attach rounds
        for match in matches:
            match.rounds = [r for r in MOCK_ROUNDS.values() if r.match_id == match.id]
            match.rounds.sort(key=lambda r: r.round_number)
        
        return matches[offset:offset + limit]
    
    def count_for_player(self, player_id: int, status: MatchStatus) -> int:
        return len([
            m for m in MOCK_MATCHES.values()
            if (m.player1_id == player_id or m.player2_id == player_id)
            and m.status == status
        ])
    
    def count_wins_for_player(self, player_id: int) -> int:
        return len([
            m for m in MOCK_MATCHES.values()
            if m.winner_id == player_id
        ])
    
    def get_leaderboard_data(self, limit: int = 100, offset: int = 0) -> List[tuple]:
        # Count wins per player
        win_counts = {}
        for match in MOCK_MATCHES.values():
            if match.winner_id:
                win_counts[match.winner_id] = win_counts.get(match.winner_id, 0) + 1
        
        # Sort by wins descending
        leaderboard = sorted(win_counts.items(), key=lambda x: x[1], reverse=True)
        return leaderboard[offset:offset + limit]


class MockRoundRepository:
    """Mock repository for round operations."""
    
    def create(self, match: MockMatch, round_number: int, category: str) -> MockRound:
        round_id = get_next_round_id()
        round_obj = MockRound(round_id, match.id, round_number, category)
        MOCK_ROUNDS[round_id] = round_obj
        return round_obj
    
    def find_current_incomplete_round(self, match_id: int) -> Optional[MockRound]:
        rounds = [r for r in MOCK_ROUNDS.values() if r.match_id == match_id]
        rounds.sort(key=lambda r: r.round_number)
        
        for round_obj in rounds:
            if round_obj.player1_card_id is None or round_obj.player2_card_id is None:
                return round_obj
        
        return None
    
    def find_completed_rounds(self, match_id: int) -> List[MockRound]:
        rounds = [
            r for r in MOCK_ROUNDS.values()
            if r.match_id == match_id
            and r.player1_card_id is not None
            and r.player2_card_id is not None
        ]
        rounds.sort(key=lambda r: r.round_number)
        return rounds


class MockDBSession:
    """Mock database session."""
    
    def commit(self):
        pass  # No-op in testing mode
    
    def rollback(self):
        pass  # No-op in testing mode


def mock_fetch_card_stats(card_ids: List[int]) -> Dict:
    """
    Mock version of _fetch_card_stats_from_ids.
    Returns card data from MOCK_CARD_CATALOGUE which is now populated from JSON.
    """
    result = {}
    for card_id in card_ids:
        if card_id not in MOCK_CARD_CATALOGUE:
            # We fail gracefully or raise depending on preference. 
            # Raising matches typical DB lookup failure behavior.
            raise ValueError(f"Card {card_id} not found in catalogue")
        result[card_id] = MOCK_CARD_CATALOGUE[card_id].copy()
    return result