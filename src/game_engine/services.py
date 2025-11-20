"""
Service layer for business logic.

Coordinates between repositories and game engine logic.
"""
import random
import requests
from typing import Dict, List, Optional
from flask import current_app

from common.extensions import db
from .game_engine import GameEngine, MoveSubmissionStatus, CARD_CATEGORIES
from .repositories import MatchRepository, RoundRepository
from .models import Match, Round, MatchStatus


class MatchService:
    """Service for match-related business operations."""
    
    def __init__(self):
        self.match_repo = MatchRepository()
        self.round_repo = RoundRepository()
        self.game_engine = GameEngine()
    
    def create_match(self, player1_id: int, player2_id: int) -> Match:
        """
        Create a new match.

        Returns:
            Match object
        
        Raises:
            ValueError: If validation fails
        """
        # Validate
        is_valid, error_msg = self.game_engine.validate_match_creation(player1_id, player2_id)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Create
        match = self.match_repo.create(player1_id, player2_id)
        db.session.commit()
        
        current_app.logger.info(f"Match {match.id} created between players {player1_id} and {player2_id}")
        return match
    
    def submit_deck(self, match_id: int, player_id: int, deck_cards: List[dict]) -> Match:
        """
        Submit a full deck and 
        validate through catalogue.

        Returns:
            Updated Match object

        Raises:
            ValueError: If validation fails with error details
            LookupError: If match not found
        """
        
        match = self.match_repo.find_by_id(match_id)
        if not match:
            raise LookupError("Match not found")

        # Validate business rules
        is_valid, error_msg = self.game_engine.validate_deck_submission(
            deck_cards, player_id, match
        )
        if not is_valid:
            raise ValueError(error_msg)

        # Validate against catalogue
        validated_deck = self._fetch_card_stats(deck_cards)

        # Store deck
        if player_id == match.player1_id:
            match.player1_deck = validated_deck
            current_app.logger.info(f"Player 1 (ID {player_id}) submitted deck.")
        else:
            match.player2_deck = validated_deck
            current_app.logger.info(f"Player 2 (ID {player_id}) submitted deck.")

        # Start match if both submitted
        if self.game_engine.should_start_match(match):
            match.status = MatchStatus.IN_PROGRESS
            self._create_new_round(match)

        db.session.commit()
        return match

    
    def submit_move(self, match_id: int, player_id: int, card_id: str) -> Dict:
        """
        Submit a move and process round if both players have moved.
        
        Returns:
            Dict with status and game state information
            
        Raises:
            ValueError: If validation fails with error details
            LookupError: If match not found
        """
        # Lock match to prevent race conditions
        match = self.match_repo.find_by_id_with_lock(match_id)
        if not match:
            raise LookupError("Match not found")
        
        # Get or find current round
        current_round = self.round_repo.find_current_incomplete_round(match_id)
        
        # Get all completed rounds for validation
        all_rounds = self.round_repo.find_completed_rounds(match_id)
        
        # Validate move
        is_valid, err = self.game_engine.validate_move_submission(
            player_id, card_id, match, current_round, all_rounds
        )
        if not is_valid:
            raise ValueError(err)
        
        # Record the move in the round
        is_player1 = player_id == match.player1_id
        if is_player1:
            current_round.player1_card_id = card_id
        else:
            current_round.player2_card_id = card_id
        
        current_app.logger.info(
            f"Move submitted: Player {player_id} played {card_id} in round {current_round.round_number}"
        )
        
        # Check if round should be processed
        is_second_move = self.game_engine.should_process_round(current_round)
        
        if not is_second_move:
            # First move - wait for opponent
            db.session.commit()
            current_app.logger.info(
                f"First move of round {current_round.round_number} submitted, waiting for opponent."
            )
            return {
                "status": MoveSubmissionStatus.WAITING_FOR_OPPONENT.value,
                "round": current_round.to_dict()
            }
        
        # Second move - process round
        result = self._process_round(match, current_round)
        db.session.commit()
        
        return result
    
    def get_match(self, match_id: int, include_rounds: bool = False) -> Match:
        """
        Get a match by ID.
        
        Raises:
            LookupError: If match not found
        """
        if include_rounds:
            match = self.match_repo.find_by_id_with_rounds(match_id)
        else:
            match = self.match_repo.find_by_id(match_id)
        
        if not match:
            raise LookupError("Match not found")
        
        return match
    
    def get_current_round_status(self, match_id: int) -> Dict:
        """Get the status of the current round."""
        match = self.get_match(match_id)
        current_round = self.round_repo.find_current_incomplete_round(match_id)
        
        if not current_round and match.status == MatchStatus.IN_PROGRESS:
            # All rounds complete but match still in progress (shouldn't happen)
            current_round = None
        
        status = self.game_engine.get_round_status(current_round)
        
        return {
            "match_id": match.id,
            "current_round_number": current_round.round_number if current_round else None,
            "current_category": current_round.category if current_round else None,
            "round_status": status.value,
            "round": current_round.to_dict() if current_round else None
        }
    
    def get_player_history(
        self,
        player_id: int,
        status: Optional[MatchStatus] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """Get match history for a player with statistics."""
        # Get matches
        matches = self.match_repo.find_for_player(player_id, status, limit, offset)
        
        # Build response with player-specific info
        history = []
        for match in matches:
            match_dict = match.to_dict(include_rounds=True)
            match_dict['player_won'] = match.winner_id == player_id if match.winner_id else None
            match_dict['player_was_player1'] = match.player1_id == player_id
            match_dict['opponent_id'] = match.player2_id if match.player1_id == player_id else match.player1_id
            match_dict['player_score'] = match.player1_score if match.player1_id == player_id else match.player2_score
            match_dict['opponent_score'] = match.player2_score if match.player1_id == player_id else match.player1_score
            history.append(match_dict)
        
        # Get summary statistics
        total_matches = self.match_repo.count_for_player(player_id, MatchStatus.FINISHED)
        total_wins = self.match_repo.count_wins_for_player(player_id)
        total_losses = total_matches - total_wins
        win_rate = (total_wins / total_matches * 100) if total_matches > 0 else 0
        
        current_app.logger.info(f"Player {player_id} history fetched: {len(matches)} matches")
        
        return {
            "player_id": player_id,
            "matches": history,
            "summary": {
                "total_matches": total_matches,
                "total_wins": total_wins,
                "total_losses": total_losses,
                "win_rate": round(win_rate, 2)
            },
            "pagination": {
                "limit": limit,
                "offset": offset,
                "count": len(matches)
            }
        }
    
    def get_leaderboard(self, limit: int = 100, offset: int = 0) -> Dict:
        """Get global leaderboard with player statistics."""
        leaderboard = self.match_repo.get_leaderboard_data(limit, offset)
        
        results = []
        for rank, (player_id, wins) in enumerate(leaderboard, start=offset + 1):
            total_matches = self.match_repo.count_for_player(player_id, MatchStatus.FINISHED)
            losses = total_matches - wins
            win_rate = (wins / total_matches * 100) if total_matches > 0 else 0
            
            results.append({
                "rank": rank,
                "player_id": player_id,
                "wins": wins,
                "losses": losses,
                "total_matches": total_matches,
                "win_rate": round(win_rate, 2)
            })
        
        current_app.logger.info(f"Leaderboard fetched: {len(results)} entries")
        
        return {
            "leaderboard": results,
            "limit": limit,
            "offset": offset,
            "count": len(results)
        }
    
    def _create_new_round(self, match: Match) -> Round:
        """Create a new round for the match."""
        round_number = self.game_engine.get_next_round_number(match)
        category = random.choice(CARD_CATEGORIES)
        
        round_obj = self.round_repo.create(match, round_number, category)
        current_app.logger.info(
            f"Created round {round_number} for match {match.id} with category {category}"
        )
        return round_obj
    
    def _process_round(self, match: Match, current_round: Round) -> Dict:
        """
        Process a complete round with both moves.
        
        Returns:
            Dict with round results
        """
        current_app.logger.info(
            f"Processing round {current_round.round_number} for match {match.id}, category: {current_round.category}"
        )
        
        # Calculate scores
        try:
            p1_score, p2_score = self.game_engine.calculate_round_scores(match, current_round)
        except KeyError as e:
            raise Exception(f"Missing card stats during round scoring: {e}")
        
        # Determine winner
        round_winner_id, is_draw = self.game_engine.calculate_round_winner(
            p1_score, p2_score, match.player1_id, match.player2_id
        )
        
        # Update round with winner
        current_round.winner_id = round_winner_id
        
        # Update match scores
        self.game_engine.update_match_scores(match, round_winner_id)
        
        # Check if match should end
        if self.game_engine.should_end_match(match):
            self.game_engine.finalize_match(match)
            current_app.logger.info(f"Match {match.id} finished. Winner={match.winner_id}")
            next_round = None
            next_category = None
        else:
            # Create next round
            next_round_obj = self._create_new_round(match)
            next_round = next_round_obj.round_number
            next_category = next_round_obj.category
            current_app.logger.info(
                f"Advancing to round {next_round}, category={next_category}"
            )
        
        return {
            "status": MoveSubmissionStatus.ROUND_PROCESSED.value,
            "round_winner_id": round_winner_id,
            "is_draw": is_draw,
            "completed_round": current_round.to_dict(),
            "scores": {
                match.player1_id: match.player1_score,
                match.player2_id: match.player2_score
            },
            "next_round": next_round,
            "next_category": next_category,
            "game_status": match.status.name
        }
    
    @staticmethod
    def _fetch_card_stats(deck_cards: List[dict]) -> Dict:
        """
        Validates full card objects with the catalogue service.
        Return cards unchanged, indexed by ID.
        """
        base_url = current_app.config.get("CATALOGUE_URL", "http://catalogue:5000").rstrip("/")
        timeout = current_app.config.get("CATALOGUE_REQUEST_TIMEOUT", 3)

        payload = { "data": deck_cards }

        try:
            response = requests.get(
                f"{base_url}/cards/validation",
                json=payload,
                timeout=timeout
            )
        except requests.RequestException as exc:
            current_app.logger.error(f"Failed to reach catalogue service: {exc}")
            raise RuntimeError("Unable to reach catalogue service") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Catalogue validation failed ({response.status_code})")

        body = response.json()
        if not body.get("data"):
            raise ValueError("Deck rejected by catalogue service (invalid cards)")

        # return deck as dict indexed by id
        return {str(card["id"]): card for card in deck_cards}
