"""
Service layer for business logic.

Coordinates between repositories and game engine logic.
"""
from typing import Dict, List, Optional, Tuple
from flask import current_app

from common.extensions import db
from .game_engine import GameEngine, MoveSubmissionStatus
from .repositories import MatchRepository, MoveRepository
from .models import Match, Move, MatchStatus

class MatchService:
    """Service for match-related business operations."""
    
    def __init__(self):
        self.match_repo = MatchRepository()
        self.move_repo = MoveRepository()
        self.game_engine = GameEngine()
    
    def create_match(self, player1_id: int, player2_id: int) -> Match:
        """
        Create a new match.
        
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
    
    def submit_deck(self, match_id: int, player_id: int, deck_card_ids: List[str]) -> Match:
        """
        Submit a deck for a player.
        
        Raises:
            ValueError: If validation fails
            LookupError: If match not found
        """
        # Find match
        match = self.match_repo.find_by_id(match_id)
        if not match:
            raise LookupError("Match not found")
        
        # Validate
        is_valid, error_msg = self.game_engine.validate_deck_submission(
            deck_card_ids, player_id, match
        )
        if not is_valid:
            raise ValueError(error_msg)
        
        # Fetch card stats (mocked for now)
        # TODO: Replace with actual catalogue service call
        deck_stats_map = self._fetch_card_stats(deck_card_ids)
        
        # Assign deck
        if player_id == match.player1_id:
            match.player1_deck = deck_stats_map
            current_app.logger.info(f"Player 1 (ID: {player_id}) deck set for match {match_id}")
        else:
            match.player2_deck = deck_stats_map
            current_app.logger.info(f"Player 2 (ID: {player_id}) deck set for match {match_id}")
        
        # Start match if both decks submitted
        if self.game_engine.should_start_match(match):
            match.status = MatchStatus.IN_PROGRESS
            current_app.logger.info(f"Match {match_id} starting - both decks submitted")
        
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
        
        # Get moves for validation
        moves_this_round = self.move_repo.find_for_match_and_round(
            match_id, match.current_round
        )
        all_player_moves = self.move_repo.find_for_player_in_match(
            match_id, player_id
        )
        
        # Validate move
        is_valid, err = self.game_engine.validate_move_submission(
            player_id, card_id, match, moves_this_round, all_player_moves
        )
        if not is_valid:
            raise ValueError(err)
        
        # Create move
        move = self.move_repo.create(match, player_id, match.current_round, card_id)
        current_app.logger.info(
            f"Move submitted: Player {player_id} played {card_id} in round {match.current_round}"
        )
        
        # Add to list for processing
        moves_this_round.append(move)
        
        # Check if round should be processed
        is_second_move = self.game_engine.should_process_round(moves_this_round)
        
        if not is_second_move:
            # First move - wait for opponent
            db.session.commit()
            current_app.logger.info(
                f"First move of round {match.current_round} submitted, waiting for opponent."
            )
            return {
                "status": MoveSubmissionStatus.WAITING_FOR_OPPONENT.value,
                "move_submitted": move.to_dict()
            }
        
        # Second move - process round
        result = self._process_round(match, moves_this_round)
        db.session.commit()
        
        return result
    
    def get_match(self, match_id: int, include_moves: bool = False) -> Match:
        """
        Get a match by ID.
        
        Raises:
            LookupError: If match not found
        """
        if include_moves:
            match = self.match_repo.find_by_id_with_moves(match_id)
        else:
            match = self.match_repo.find_by_id(match_id)
        
        if not match:
            raise LookupError("Match not found")
        
        return match
    
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
            match_dict = match.to_dict(include_moves=True)
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
    
    def _process_round(self, match: Match, moves_this_round: List[Move]) -> Dict:
        """
        Process a complete round with both moves.
        
        Returns:
            Dict with round results
        """
        try:
            p1_move = next(m for m in moves_this_round if m.player_id == match.player1_id)
            p2_move = next(m for m in moves_this_round if m.player_id == match.player2_id)
        except StopIteration:
            raise Exception("Required moves for both players not found.")
        
        category = match.current_round_category
        current_app.logger.info(
            f"Processing round {match.current_round} for match {match.id}, category: {category}"
        )
        
        # Calculate scores
        try:
            p1_score, p2_score = self.game_engine.calculate_round_scores(
                match, p1_move, p2_move, category
            )
        except KeyError as e:
            raise Exception(f"Missing card stats during round scoring: {e}")
        
        # Determine winner
        round_winner_id, is_draw = self.game_engine.calculate_round_winner(
            p1_score, p2_score, match.player1_id, match.player2_id
        )
        
        # Update scores
        self.game_engine.update_match_scores(match, round_winner_id)
        
        # Check if match should end
        if self.game_engine.should_end_match(match):
            self.game_engine.finalize_match(match)
            current_app.logger.info(f"Match {match.id} finished. Winner={match.winner_id}")
        else:
            self.game_engine.advance_to_next_round(match)
            current_app.logger.info(
                f"Advancing to round {match.current_round}, next category={match.current_round_category}"
            )
        
        return {
            "status": MoveSubmissionStatus.ROUND_PROCESSED.value,
            "round_winner_id": round_winner_id,
            "is_draw": is_draw,
            "moves": [p1_move.to_dict(), p2_move.to_dict()],
            "scores": {
                match.player1_id: match.player1_score,
                match.player2_id: match.player2_score
            },
            "next_round": match.current_round,
            "next_category": match.current_round_category,
            "game_status": match.status.name
        }
    
    @staticmethod
    def _fetch_card_stats(deck_card_ids: List[str]) -> Dict:
        """
        Fetch card stats from catalogue service.
        
        TODO: Replace with actual API call.
        """
        import random
        deck_stats_map = {}
        for card_id in deck_card_ids:
            deck_stats_map[card_id] = {
                "economy": random.randint(5, 15),
                "food": random.randint(5, 15),
                "environment": random.randint(5, 15),
                "special": random.randint(0, 5),
                "total": random.uniform(20.0, 40.0)
            }
        return deck_stats_map