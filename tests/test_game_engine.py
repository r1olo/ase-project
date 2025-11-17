# tests/test_game_engine_logic.py

import pytest
from game_engine.game_engine import GameEngine, RoundStatus  # Assuming your logic is here
from game_engine.models import Match, Move, MatchStatus

# --- Stub/Mock Objects ---
# We don't need a DB; just create the Python objects
# These objects act as "stubs" for your logic functions.

@pytest.fixture
def base_match():
    """A simple Match object in the IN_PROGRESS state."""
    match = Match(player1_id=100, player2_id=200)
    match.status = MatchStatus.IN_PROGRESS
    
    # Define the mock decks as they would be after fetching from 'catalogue'
    match.player1_deck = {
        "card_abruzzo": {"economy": 5, "food": 5, "environment": 6, "special": 7, "total": 5.8},
        "card_lazio": {"economy": 8, "food": 8, "environment": 6, "special": 10, "total": 8.0},
    }
    match.player2_deck = {
        "card_sicilia": {"economy": 2, "food": 9, "environment": 10, "special": 10, "total": 7.8},
        "card_veneto": {"economy": 8, "food": 7, "environment": 8, "special": 6, "total": 7.3},
    }
    return match

@pytest.fixture
def p1_move(base_match):
    """A move for player 1 playing 'card_lazio'."""
    return Move(
        match=base_match,
        player_id=100,
        round_number=1,
        card_id="card_lazio"
    )

@pytest.fixture
def p2_move(base_match):
    """A move for player 2 playing 'card_sicilia'."""
    return Move(
        match=base_match,
        player_id=200,
        round_number=1,
        card_id="card_sicilia"
    )

# --- Unit Tests for GameEngine Logic ---

def test_calculate_round_scores(base_match, p1_move, p2_move):
    """
    Tests score calculation for a specific category.
    """
    category = "economy"
    
    # P1 (Lazio) has economy: 8
    # P2 (Sicilia) has economy: 2
    p1_score, p2_score = GameEngine.calculate_round_scores(
        base_match, p1_move, p2_move, category
    )
    
    assert p1_score == 8
    assert p2_score == 2

def test_calculate_round_scores_draw(base_match, p1_move, p2_move):
    """
    Tests score calculation for a draw category.
    """
    category = "special" 
    
    # P1 (Lazio) has special: 10
    # P2 (Sicilia) has special: 10
    p1_score, p2_score = GameEngine.calculate_round_scores(
        base_match, p1_move, p2_move, category
    )
    
    assert p1_score == 10
    assert p2_score == 10

def test_calculate_round_winner(base_match):
    """
    Tests the logic for determining the round winner.
    """
    # P1 wins
    winner_id, is_draw = GameEngine.calculate_round_winner(10, 5, 100, 200)
    assert winner_id == 100
    assert is_draw is False
    
    # P2 wins
    winner_id, is_draw = GameEngine.calculate_round_winner(5, 10, 100, 200)
    assert winner_id == 200
    assert is_draw is False
    
    # Draw
    winner_id, is_draw = GameEngine.calculate_round_winner(10, 10, 100, 200)
    assert winner_id is None
    assert is_draw is True

def test_finalize_match_winner(base_match):
    """
    Tests that finalizing the match sets the correct winner.
    """
    base_match.player1_score = 5
    base_match.player2_score = 3
    
    GameEngine.finalize_match(base_match)
    
    assert base_match.status == MatchStatus.FINISHED
    assert base_match.winner_id == 100

def test_finalize_match_draw(base_match):
    """
    Tests that finalizing the match correctly handles a draw.
    """
    base_match.player1_score = 4
    base_match.player2_score = 4
    
    GameEngine.finalize_match(base_match)
    
    assert base_match.status == MatchStatus.FINISHED
    assert base_match.winner_id is None

def test_advance_to_next_round(base_match):
    """
    Tests advancing to the next round.
    """
    GameEngine.advance_to_next_round(base_match)
    
    assert base_match.current_round == 2
    assert base_match.current_round_category is not None

def test_get_round_status_waiting(base_match):
    """
    Tests that the round status is WAITING when not all moves are in.
    """
    status = GameEngine.get_round_status(base_match, 1)
    assert status == RoundStatus.WAITING_FOR_BOTH_PLAYERS       

def test_get_round_status_complete(base_match):
    """
    Tests that the round status is COMPLETE when all moves are in.
    """
    status = GameEngine.get_round_status(base_match, 2)
    assert status == RoundStatus.ROUND_COMPLETE

    