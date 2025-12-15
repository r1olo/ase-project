"""
Unit tests for GameEngine class.

Tests all static methods with various scenarios including edge cases.
"""
import pytest
from unittest.mock import Mock
from game_engine.game_engine import GameEngine, RoundStatus, ValidationError
from game_engine.models import MatchStatus


# --- Fixtures ---

@pytest.fixture
def setup_match():
    """Create a basic match in SETUP status."""
    match = Mock()
    match.player1_id = 1
    match.player2_id = 2
    match.status = MatchStatus.SETUP
    match.player1_deck = None
    match.player2_deck = None
    match.player1_score = 0
    match.player2_score = 0
    match.rounds = []
    return match


@pytest.fixture
def in_progress_match():
    """Create a match in IN_PROGRESS status with decks."""
    match = Mock()
    match.player1_id = 1
    match.player2_id = 2
    match.status = MatchStatus.IN_PROGRESS
    match.player1_deck = {
        101: {"attack": 10, "defense": 5, "speed": 8},
        102: {"attack": 7, "defense": 9, "speed": 6},
        103: {"attack": 12, "defense": 4, "speed": 9},
        104: {"attack": 6, "defense": 11, "speed": 5},
        105: {"attack": 9, "defense": 7, "speed": 10}
    }
    match.player2_deck = {
        201: {"attack": 8, "defense": 8, "speed": 7},
        202: {"attack": 11, "defense": 6, "speed": 8},
        203: {"attack": 5, "defense": 10, "speed": 6},
        204: {"attack": 10, "defense": 5, "speed": 9},
        205: {"attack": 7, "defense": 9, "speed": 11}
    }
    match.player1_score = 0
    match.player2_score = 0
    match.rounds = []
    return match


@pytest.fixture
def current_round():
    """Create an empty round."""
    round_obj = Mock()
    round_obj.round_number = 1
    round_obj.player1_card_id = None
    round_obj.player2_card_id = None
    round_obj.category = "attack"
    round_obj.is_complete = Mock(return_value=False)
    return round_obj


# --- Test validate_match_creation ---

class TestValidateMatchCreation:
    def test_valid_match_creation(self):
        is_valid, error = GameEngine.validate_match_creation(1, 2)
        assert is_valid is True
        assert error is None
    
    def test_same_player_ids(self):
        is_valid, error = GameEngine.validate_match_creation(1, 1)
        assert is_valid is False
        assert "different" in error.lower()
    
    def test_invalid_player1_type(self):
        is_valid, error = GameEngine.validate_match_creation("abc", 2)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_invalid_player2_type(self):
        is_valid, error = GameEngine.validate_match_creation(1, "xyz")
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_string_numbers_rejected(self):
        # Strings are no longer converted - must be strict integers
        is_valid, error = GameEngine.validate_match_creation("1", "2")
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_boolean_not_accepted(self):
        is_valid, error = GameEngine.validate_match_creation(True, False)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_both_booleans_rejected(self):
        is_valid, error = GameEngine.validate_match_creation(True, True)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_negative_player1_id(self):
        is_valid, error = GameEngine.validate_match_creation(-1, 2)
        assert is_valid is False
        assert "non-negative" in error.lower()
    
    def test_negative_player2_id(self):
        is_valid, error = GameEngine.validate_match_creation(1, -2)
        assert is_valid is False
        assert "non-negative" in error.lower()


# --- Test validate_deck_submission ---

class TestValidateDeckSubmission:
    def test_valid_deck_submission(self, setup_match):
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is True
        assert error is None
    
    def test_invalid_player_id_type(self, setup_match):
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, "abc", setup_match)
        assert is_valid is False
        assert "required" in error.lower() or "integer" in error.lower()
    
    def test_invalid_deck_type(self, setup_match):
        is_valid, error = GameEngine.validate_deck_submission("not a list", 1, setup_match)
        assert is_valid is False
        assert "list" in error.lower()
    
    def test_deck_with_non_integer_ids(self, setup_match):
        # String numbers get normalized to integers, so test with actual non-numeric strings
        deck = [101, "abc", 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_empty_deck(self, setup_match):
        is_valid, error = GameEngine.validate_deck_submission([], 1, setup_match)
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_wrong_match_status(self, setup_match):
        setup_match.status = MatchStatus.IN_PROGRESS
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "SETUP" in error
    
    def test_player_not_in_match(self, setup_match):
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 999, setup_match)
        assert is_valid is False
        assert "not part" in error.lower()
    
    def test_wrong_deck_size_too_small(self, setup_match):
        deck = [101, 102, 103]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "5 cards" in error
    
    def test_wrong_deck_size_too_large(self, setup_match):
        deck = [101, 102, 103, 104, 105, 106]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "5 cards" in error
    
    def test_duplicate_cards(self, setup_match):
        deck = [101, 102, 103, 104, 104]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "duplicate" in error.lower()
    
    def test_boolean_player_id_rejected(self, setup_match):
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, True, setup_match)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_boolean_in_deck_rejected(self, setup_match):
        deck = [101, 102, True, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "integer" in error.lower()
    
    def test_negative_player_id(self, setup_match):
        deck = [101, 102, 103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, -1, setup_match)
        assert is_valid is False
        assert "non-negative" in error.lower()
    
    def test_negative_card_in_deck(self, setup_match):
        deck = [101, 102, -103, 104, 105]
        is_valid, error = GameEngine.validate_deck_submission(deck, 1, setup_match)
        assert is_valid is False
        assert "non-negative" in error.lower()


# --- Test should_start_match ---

class TestShouldStartMatch:
    def test_both_decks_submitted(self, setup_match):
        setup_match.player1_deck = [101, 102, 103, 104, 105]
        setup_match.player2_deck = [201, 202, 203, 204, 205]
        assert GameEngine.should_start_match(setup_match) is True
    
    def test_only_player1_deck(self, setup_match):
        setup_match.player1_deck = [101, 102, 103, 104, 105]
        assert GameEngine.should_start_match(setup_match) is False
    
    def test_only_player2_deck(self, setup_match):
        setup_match.player2_deck = [201, 202, 203, 204, 205]
        assert GameEngine.should_start_match(setup_match) is False
    
    def test_no_decks(self, setup_match):
        assert GameEngine.should_start_match(setup_match) is False


# --- Test validate_move_submission ---

class TestValidateMoveSubmission:
    def test_valid_move_submission(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            1, 101, in_progress_match, current_round, []
        )
        assert is_valid is True
        assert error is None
    
    def test_invalid_player_id_type(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            "abc", 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
    
    def test_invalid_card_id_type(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            1, "abc", in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
    
    def test_match_not_in_progress(self, in_progress_match, current_round):
        in_progress_match.status = MatchStatus.FINISHED
        is_valid, error = GameEngine.validate_move_submission(
            1, 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.WRONG_STATUS.value
    
    def test_player_not_in_match(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            999, 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.NOT_PARTICIPANT.value
    
    def test_no_deck(self, in_progress_match, current_round):
        in_progress_match.player1_deck = None
        is_valid, error = GameEngine.validate_move_submission(
            1, 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.NO_DECK.value
    
    def test_card_not_in_deck(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            1, 999, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.CARD_NOT_IN_DECK.value
    
    def test_already_moved_this_round_player1(self, in_progress_match, current_round):
        current_round.player1_card_id = 101
        is_valid, error = GameEngine.validate_move_submission(
            1, 102, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.ALREADY_MOVED_THIS_ROUND.value
    
    def test_already_moved_this_round_player2(self, in_progress_match, current_round):
        current_round.player2_card_id = 201
        is_valid, error = GameEngine.validate_move_submission(
            2, 202, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.ALREADY_MOVED_THIS_ROUND.value
    
    def test_card_already_played_in_previous_round(self, in_progress_match, current_round):
        previous_round = Mock()
        previous_round.player1_card_id = 101
        previous_round.player2_card_id = 201
        
        is_valid, error = GameEngine.validate_move_submission(
            1, 101, in_progress_match, current_round, [previous_round]
        )
        assert is_valid is False
        assert error["code"] == ValidationError.CARD_ALREADY_PLAYED.value
    
    def test_string_card_id_in_deck(self, in_progress_match, current_round):
        # Test when deck has string keys
        in_progress_match.player1_deck = {
            "101": {"attack": 10, "defense": 5, "speed": 8},
            "102": {"attack": 7, "defense": 9, "speed": 6},
            "103": {"attack": 12, "defense": 4, "speed": 9},
            "104": {"attack": 6, "defense": 11, "speed": 5},
            "105": {"attack": 9, "defense": 7, "speed": 10}
        }
        is_valid, error = GameEngine.validate_move_submission(
            1, 101, in_progress_match, current_round, []
        )
        assert is_valid is True
    
    def test_boolean_player_id_rejected(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            True, 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
        assert "integer" in error["msg"].lower()
    
    def test_boolean_card_id_rejected(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            1, False, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
        assert "integer" in error["msg"].lower()
    
    def test_negative_player_id(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            -1, 101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
        assert "non-negative" in error["msg"].lower()
    
    def test_negative_card_id(self, in_progress_match, current_round):
        is_valid, error = GameEngine.validate_move_submission(
            1, -101, in_progress_match, current_round, []
        )
        assert is_valid is False
        assert error["code"] == ValidationError.INVALID_TYPES.value
        assert "non-negative" in error["msg"].lower()


# --- Test should_process_round ---

class TestShouldProcessRound:
    def test_both_players_moved(self, current_round):
        current_round.is_complete = Mock(return_value=True)
        assert GameEngine.should_process_round(current_round) is True
    
    def test_only_one_player_moved(self, current_round):
        current_round.is_complete = Mock(return_value=False)
        assert GameEngine.should_process_round(current_round) is False


# --- Test get_card_stats ---

class TestGetCardStats:
    def test_get_card_stats_player1_int_key(self, in_progress_match):
        stats = GameEngine.get_card_stats(in_progress_match, 1, 101)
        assert stats == {"attack": 10, "defense": 5, "speed": 8}
    
    def test_get_card_stats_player2_int_key(self, in_progress_match):
        stats = GameEngine.get_card_stats(in_progress_match, 2, 201)
        assert stats == {"attack": 8, "defense": 8, "speed": 7}
    
    def test_get_card_stats_string_key(self, in_progress_match):
        in_progress_match.player1_deck = {
            "101": {"attack": 10, "defense": 5, "speed": 8}
        }
        stats = GameEngine.get_card_stats(in_progress_match, 1, "101")
        assert stats == {"attack": 10, "defense": 5, "speed": 8}


# --- Test calculate_round_scores ---

class TestCalculateRoundScores:
    def test_calculate_round_scores_attack(self, in_progress_match, current_round):
        current_round.player1_card_id = 101
        current_round.player2_card_id = 201
        current_round.category = "attack"
        
        score_p1, score_p2 = GameEngine.calculate_round_scores(
            in_progress_match, current_round
        )
        assert score_p1 == 10
        assert score_p2 == 8
    
    def test_calculate_round_scores_defense(self, in_progress_match, current_round):
        current_round.player1_card_id = 102
        current_round.player2_card_id = 203
        current_round.category = "defense"
        
        score_p1, score_p2 = GameEngine.calculate_round_scores(
            in_progress_match, current_round
        )
        assert score_p1 == 9
        assert score_p2 == 10
    
    def test_calculate_round_scores_speed(self, in_progress_match, current_round):
        current_round.player1_card_id = 105
        current_round.player2_card_id = 205
        current_round.category = "speed"
        
        score_p1, score_p2 = GameEngine.calculate_round_scores(
            in_progress_match, current_round
        )
        assert score_p1 == 10
        assert score_p2 == 11


# --- Test calculate_round_winner ---

class TestCalculateRoundWinner:
    def test_player1_wins(self):
        winner_id, is_draw = GameEngine.calculate_round_winner(10, 8, 1, 2)
        assert winner_id == 1
        assert is_draw is False
    
    def test_player2_wins(self):
        winner_id, is_draw = GameEngine.calculate_round_winner(7, 9, 1, 2)
        assert winner_id == 2
        assert is_draw is False
    
    def test_draw(self):
        winner_id, is_draw = GameEngine.calculate_round_winner(8, 8, 1, 2)
        assert winner_id is None
        assert is_draw is True


# --- Test update_match_scores ---

class TestUpdateMatchScores:
    def test_player1_wins_round(self, in_progress_match):
        GameEngine.update_match_scores(in_progress_match, 1)
        assert in_progress_match.player1_score == 1
        assert in_progress_match.player2_score == 0
    
    def test_player2_wins_round(self, in_progress_match):
        GameEngine.update_match_scores(in_progress_match, 2)
        assert in_progress_match.player1_score == 0
        assert in_progress_match.player2_score == 1
    
    def test_draw_round(self, in_progress_match):
        GameEngine.update_match_scores(in_progress_match, None)
        assert in_progress_match.player1_score == 0
        assert in_progress_match.player2_score == 0
    
    def test_multiple_rounds(self, in_progress_match):
        GameEngine.update_match_scores(in_progress_match, 1)
        GameEngine.update_match_scores(in_progress_match, 2)
        GameEngine.update_match_scores(in_progress_match, 1)
        assert in_progress_match.player1_score == 2
        assert in_progress_match.player2_score == 1


# --- Test should_end_match ---

class TestShouldEndMatch:
    def test_no_rounds_completed(self, in_progress_match):
        assert GameEngine.should_end_match(in_progress_match) is False
    
    def test_less_than_max_rounds(self, in_progress_match):
        for i in range(3):
            round_obj = Mock()
            round_obj.is_complete = Mock(return_value=True)
            in_progress_match.rounds.append(round_obj)
        assert GameEngine.should_end_match(in_progress_match) is False
    
    def test_exactly_max_rounds(self, in_progress_match):
        for i in range(5):
            round_obj = Mock()
            round_obj.is_complete = Mock(return_value=True)
            in_progress_match.rounds.append(round_obj)
        assert GameEngine.should_end_match(in_progress_match) is True
    
    def test_incomplete_rounds_not_counted(self, in_progress_match):
        for i in range(3):
            round_obj = Mock()
            round_obj.is_complete = Mock(return_value=True)
            in_progress_match.rounds.append(round_obj)
        
        incomplete_round = Mock()
        incomplete_round.is_complete = Mock(return_value=False)
        in_progress_match.rounds.append(incomplete_round)
        
        assert GameEngine.should_end_match(in_progress_match) is False


# --- Test determine_match_winner ---

class TestDetermineMatchWinner:
    def test_player1_wins_match(self):
        winner_id = GameEngine.determine_match_winner(3, 2, 1, 2)
        assert winner_id == 1
    
    def test_player2_wins_match(self):
        winner_id = GameEngine.determine_match_winner(1, 4, 1, 2)
        assert winner_id == 2
    
    def test_match_draw(self):
        winner_id = GameEngine.determine_match_winner(2, 2, 1, 2)
        assert winner_id is None


# --- Test finalize_match ---

class TestFinalizeMatch:
    def test_finalize_match_player1_wins(self, in_progress_match):
        in_progress_match.player1_score = 3
        in_progress_match.player2_score = 2
        in_progress_match.winner_id = None
        
        GameEngine.finalize_match(in_progress_match)
        assert in_progress_match.status == MatchStatus.FINISHED
        assert in_progress_match.winner_id == 1
    
    def test_finalize_match_player2_wins(self, in_progress_match):
        in_progress_match.player1_score = 1
        in_progress_match.player2_score = 4
        in_progress_match.winner_id = None
        
        GameEngine.finalize_match(in_progress_match)
        assert in_progress_match.status == MatchStatus.FINISHED
        assert in_progress_match.winner_id == 2
    
    def test_finalize_match_draw(self, in_progress_match):
        in_progress_match.player1_score = 2
        in_progress_match.player2_score = 2
        in_progress_match.winner_id = None
        
        GameEngine.finalize_match(in_progress_match)
        assert in_progress_match.status == MatchStatus.FINISHED
        assert in_progress_match.winner_id is None


# --- Test get_next_round_number ---

class TestGetNextRoundNumber:
    def test_first_round(self, in_progress_match):
        round_number = GameEngine.get_next_round_number(in_progress_match)
        assert round_number == 1
    
    def test_subsequent_rounds(self, in_progress_match):
        for i in range(3):
            round_obj = Mock()
            round_obj.is_complete = Mock(return_value=True)
            in_progress_match.rounds.append(round_obj)
        
        round_number = GameEngine.get_next_round_number(in_progress_match)
        assert round_number == 4
    
    def test_with_incomplete_round(self, in_progress_match):
        for i in range(2):
            round_obj = Mock()
            round_obj.is_complete = Mock(return_value=True)
            in_progress_match.rounds.append(round_obj)
        
        incomplete_round = Mock()
        incomplete_round.is_complete = Mock(return_value=False)
        in_progress_match.rounds.append(incomplete_round)
        
        round_number = GameEngine.get_next_round_number(in_progress_match)
        assert round_number == 3


# --- Test get_round_status ---

class TestGetRoundStatus:
    def test_no_current_round(self):
        status = GameEngine.get_round_status(None)
        assert status == RoundStatus.WAITING_FOR_BOTH_PLAYERS
    
    def test_waiting_for_both_players(self, current_round):
        current_round.player1_card_id = None
        current_round.player2_card_id = None
        status = GameEngine.get_round_status(current_round)
        assert status == RoundStatus.WAITING_FOR_BOTH_PLAYERS
    
    def test_waiting_for_one_player(self, current_round):
        current_round.player1_card_id = 101
        current_round.player2_card_id = None
        current_round.is_complete = Mock(return_value=False)
        status = GameEngine.get_round_status(current_round)
        assert status == RoundStatus.WAITING_FOR_ONE_PLAYER
    
    def test_round_complete(self, current_round):
        current_round.player1_card_id = 101
        current_round.player2_card_id = 201
        current_round.is_complete = Mock(return_value=True)
        status = GameEngine.get_round_status(current_round)
        assert status == RoundStatus.ROUND_COMPLETE