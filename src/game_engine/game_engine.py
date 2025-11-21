"""
Game Engine - Core business logic.

This module contains all game rules and calculations.
All methods are static as this is a stateless service.
"""
import random
from typing import Any, Dict, Optional, Tuple, List
from enum import Enum

from .models import Match, MatchStatus, Round, CARD_CATEGORIES

# --- Constants ---

MAX_ROUNDS = 10 
DECK_SIZE = 10

# --- Enums ---

class RoundStatus(Enum):
    """Status of the current round."""
    WAITING_FOR_BOTH_PLAYERS = "WAITING_FOR_BOTH_PLAYERS"
    WAITING_FOR_ONE_PLAYER = "WAITING_FOR_ONE_PLAYER"
    ROUND_COMPLETE = "ROUND_COMPLETE"


class MoveSubmissionStatus(Enum):
    """Status returned after move submission."""
    WAITING_FOR_OPPONENT = "WAITING_FOR_OPPONENT"
    ROUND_PROCESSED = "ROUND_PROCESSED"


class ValidationError(Enum):
    """Error codes for validation failures."""
    INVALID_TYPES = "INVALID_TYPES"
    SAME_PLAYER = "SAME_PLAYER"
    EMPTY_DECK = "EMPTY_DECK"
    WRONG_STATUS = "WRONG_STATUS"
    NOT_PARTICIPANT = "NOT_PARTICIPANT"
    WRONG_DECK_SIZE = "WRONG_DECK_SIZE"
    DUPLICATE_CARDS = "DUPLICATE_CARDS"
    CARD_NOT_IN_DECK = "CARD_NOT_IN_DECK"
    ALREADY_MOVED_THIS_ROUND = "ALREADY_MOVED_THIS_ROUND"
    CARD_ALREADY_PLAYED = "CARD_ALREADY_PLAYED"
    NO_DECK = "NO_DECK"


class GameEngine:
    """
    Core game logic service. Handles all business rules and calculations.
    All methods are static as this is a stateless service.
    """
    
    @staticmethod
    def validate_match_creation(player1_id: Any, player2_id: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate match creation parameters.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not isinstance(player1_id, int) or not isinstance(player2_id, int):
            return False, "player1_id and player2_id must be integers"
        
        if player1_id == player2_id:
            return False, "Player IDs must be different"
        
        return True, None
    
    @staticmethod
    def validate_deck_submission(deck_card_ids: List[str], player_id: int, match: Match) -> Tuple[bool, Optional[str]]:

        """
        Validate a deck submission with all business rules.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Type validation
        if not isinstance(player_id, int) or not isinstance(deck_card_ids, list):
            return False, "player_id (int) and deck (list) are required"
        
        if not deck_card_ids:
            return False, "Deck cannot be empty"
        
        # Match status validation
        if match.status != MatchStatus.SETUP:
            return False, "Decks can only be chosen during SETUP"
        
        # Player validation
        if player_id not in [match.player1_id, match.player2_id]:
            return False, "Player is not part of this match"
        
        # Deck size validation
        if len(deck_card_ids) != DECK_SIZE:
            return False, f"Deck must contain {DECK_SIZE} cards"
        
        # Uniqueness validation
        if len(deck_card_ids) != len(set(deck_card_ids)):
            return False, "Deck cannot contain duplicate cards"
        
        return True, None
    
    @staticmethod
    def should_start_match(match: Match) -> bool:
        """
        Determine if both players have submitted decks and match should start.
        """
        return match.player1_deck is not None and match.player2_deck is not None
    
    @staticmethod
    def validate_move_submission(
        player_id: Any, 
        card_id: Any, 
        match: Match, 
        current_round: Optional[Round],
        all_rounds: List[Round]
    ) -> Tuple[bool, Optional[Dict[str, str]]]:
        """
        Validate a move submission with all business rules.
        
        Args:
            player_id: ID of the player submitting the move
            card_id: ID of the card being played
            match: The Match object
            current_round: The current Round object (may be None if just created)
            all_rounds: List of all completed rounds in this match
        
        Returns:
            Tuple of (is_valid, error_dict with msg and code)
        """
        # Type validation
        if not isinstance(player_id, int) or not isinstance(card_id, int):
            return False, {
                "msg": "player_id (int) and card_id (int) are required",
                "code": ValidationError.INVALID_TYPES.value
            }
        
        # Match status validation
        if match.status != MatchStatus.IN_PROGRESS:
            return False, {
                "msg": "Match is not in progress",
                "code": ValidationError.WRONG_STATUS.value
            }
        
        # Player validation
        if player_id not in [match.player1_id, match.player2_id]:
            return False, {
                "msg": "Player is not part of this match",
                "code": ValidationError.NOT_PARTICIPANT.value
            }
        
        # Deck validation
        player_deck = match.player1_deck if player_id == match.player1_id else match.player2_deck
        if not player_deck:
            return False, {
                "msg": "Player deck not found or not set",
                "code": ValidationError.NO_DECK.value
            }
        
        # Card in deck validation
        if card_id not in player_deck:
            return False, {
                "msg": f"Card {card_id} is not in the player's deck",
                "code": ValidationError.CARD_NOT_IN_DECK.value
            }
        
        # Already submitted this round validation
        if current_round:
            is_player1 = player_id == match.player1_id
            if is_player1 and current_round.player1_card_id is not None:
                return False, {
                    "msg": "Player has already submitted a move for this round",
                    "code": ValidationError.ALREADY_MOVED_THIS_ROUND.value
                }
            if not is_player1 and current_round.player2_card_id is not None:
                return False, {
                    "msg": "Player has already submitted a move for this round",
                    "code": ValidationError.ALREADY_MOVED_THIS_ROUND.value
                }
        
        # Card already played validation (check all previous rounds)
        for round_obj in all_rounds:
            if card_id in [round_obj.player1_card_id, round_obj.player2_card_id]:
                return False, {
                    "msg": f"Card {card_id} has already been played",
                    "code": ValidationError.CARD_ALREADY_PLAYED.value
                }
        
        return True, None
    
    @staticmethod
    def should_process_round(current_round: Round) -> bool:
        """
        Determine if the round should be processed (both players have moved).

        Returns:
            True if both players have submitted cards
        """
        return current_round.is_complete()
    
    @staticmethod
    def get_card_stats(match: Match, player_id: int, card_id: str) -> Dict[str, float]:
        """
        Retrieve card stats from the match's deck data.
        
        Args:
            match: The Match object
            player_id: ID of the player
            card_id: ID of the card
            
        Returns:
            Dictionary of card stats
            
        Raises:
            KeyError: If card not found in deck
        """
        deck = match.player1_deck if player_id == match.player1_id else match.player2_deck
        return deck[card_id]
    
    @staticmethod
    def calculate_round_scores(
        match: Match, 
        current_round: Round
    ) -> Tuple[float, float]:
        """
        Calculate the scores for both players in a round.
        
        Returns:
            Tuple of (score_p1, score_p2)
        """
        p1_card_stats = GameEngine.get_card_stats(match, match.player1_id, current_round.player1_card_id)
        p2_card_stats = GameEngine.get_card_stats(match, match.player2_id, current_round.player2_card_id)
        
        category = current_round.category
        score_p1 = p1_card_stats[category]
        score_p2 = p2_card_stats[category]
        
        return score_p1, score_p2
    
    @staticmethod
    def calculate_round_winner(
        score_p1: float, 
        score_p2: float, 
        player1_id: int, 
        player2_id: int
    ) -> Tuple[Optional[int], bool]:
        """
        Determine the winner of a round.
        
        Returns:
            Tuple of (winner_id or None, is_draw)
        """
        if score_p1 > score_p2:
            return player1_id, False
        elif score_p2 > score_p1:
            return player2_id, False
        else:
            # It's a draw
            return None, True
    
    @staticmethod
    def update_match_scores(match: Match, round_winner_id: Optional[int]) -> None:
        """
        Update match scores based on round winner.
        Mutates the match object.
        """
        if round_winner_id == match.player1_id:
            match.player1_score += 1
        elif round_winner_id == match.player2_id:
            match.player2_score += 1
        # If round_winner_id is None (draw), no score change
    
    @staticmethod
    def should_end_match(match: Match) -> bool:
        """
        Determine if the match should end based on number of completed rounds.
        """
        return len([r for r in match.rounds if r.is_complete()]) >= MAX_ROUNDS
    
    @staticmethod
    def determine_match_winner(
        player1_score: int, 
        player2_score: int,
        player1_id: int, 
        player2_id: int
    ) -> Optional[int]:
        """
        Determine the winner of the entire match.
        
        Returns:
            winner_id or None for a draw
        """
        if player1_score > player2_score:
            return player1_id
        elif player2_score > player1_score:
            return player2_id
        else:
            return None  # Match ended in a draw
    
    @staticmethod
    def finalize_match(match: Match) -> None:
        """
        Finalize match by setting status and winner.
        Mutates the match object.
        """
        match.status = MatchStatus.FINISHED
        match.winner_id = GameEngine.determine_match_winner(
            match.player1_score, match.player2_score,
            match.player1_id, match.player2_id
        )
    
    @staticmethod
    def get_next_round_number(match: Match) -> int:
        """
        Get the round number for the next round.
        """
        return len([r for r in match.rounds if r.is_complete()]) + 1
    
    @staticmethod
    def get_round_status(current_round: Optional[Round]) -> RoundStatus:
        """
        Get the current round status.
        """
        if not current_round:
            return RoundStatus.WAITING_FOR_BOTH_PLAYERS
        
        if current_round.player1_card_id is None and current_round.player2_card_id is None:
            return RoundStatus.WAITING_FOR_BOTH_PLAYERS
        elif not current_round.is_complete():
            return RoundStatus.WAITING_FOR_ONE_PLAYER
        else:
            return RoundStatus.ROUND_COMPLETE