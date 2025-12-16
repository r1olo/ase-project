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
        self._db_session = db.session
        self.game_engine = GameEngine()

    def _is_testing(self) -> bool:
        """Check if we're in testing mode."""
        try:
            return current_app.config.get("TESTING", False)
        except RuntimeError:
            # No app context, default to False
            return False

    def _get_db_session(self):
        """Get DB session."""
        return self._db_session

    
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
        self._get_db_session().commit()
        
        current_app.logger.info(f"Match {match.id} created between players {player1_id} and {player2_id}")
        return match
    
    def submit_deck(self, match_id: int, player_id: int, deck_card_ids: List[int]) -> Match:
        match = self.match_repo.find_by_id(match_id)
        if not match:
            raise LookupError("Match not found")

        # Validate business rules (still checks duplicates, size, etc.)
        is_valid, error_msg = self.game_engine.validate_deck_submission(
            deck_card_ids, player_id, match
        )
        if not is_valid:
            raise ValueError(error_msg)

        # Fetch card stats (will use mock in testing mode)
        validated_deck = self._fetch_card_stats_from_ids(deck_card_ids)

        # Store deck
        if player_id == match.player1_id:
            match.player1_deck = validated_deck
        else:
            match.player2_deck = validated_deck

        # Start match if both submitted
        if self.game_engine.should_start_match(match):
            match.status = MatchStatus.IN_PROGRESS
            self._create_new_round(match)

        self._get_db_session().commit()
        return match
    
    def submit_move(self, match_id: int, player_id: int, card_id: int, round_number: int) -> Dict:
        """
        Submit a move for a specific round, ensuring that the round number matches
        the currently active round.
        """
        
        # Lock match for concurrency
        match = self.match_repo.find_by_id_with_lock(match_id)
        if not match:
            raise LookupError("Match not found")

        # Determine what round is currently expected
        expected_round = self.round_repo.find_current_incomplete_round(match_id)

        if not expected_round:
            raise ValueError("No active round available")

        # Validate the round number matches the expected round
        if expected_round.round_number != round_number:
            raise ValueError(f"Move submitted for wrong round. Expected round {expected_round.round_number}, got {round_number}")

        # Now fetch that round explicitly
        current_round = expected_round

        # Fetch completed rounds for validation
        all_rounds = self.round_repo.find_completed_rounds(match_id)

        is_valid, err = self.game_engine.validate_move_submission(
            player_id, card_id, match, current_round, all_rounds
        )
        if not is_valid:
            raise ValueError(err)

        # Record move
        is_player1 = player_id == match.player1_id
        if is_player1:
            current_round.player1_card_id = card_id
        else:
            current_round.player2_card_id = card_id

        current_app.logger.info(
            f"Player {player_id} played card {card_id} in round {current_round.round_number}"
        )

        # Check if the round is now complete
        is_second_move = self.game_engine.should_process_round(current_round)

        if not is_second_move:
            self._get_db_session().commit()
            return {
                "status": MoveSubmissionStatus.WAITING_FOR_OPPONENT.value,
                "round": current_round.to_dict()
            }

        # Process completed round
        result = self._process_round(match, current_round)
        self._get_db_session().commit()

        return result
    
    def get_match(self, match_id: int, requester_id: int, include_rounds: bool = False) -> Match:
        """
        Get a match by ID.
        
        Raises:
            LookupError: If match not found
        """
        if include_rounds:
            match = self.match_repo.find_by_id_with_rounds(match_id)
        else:
            match = self.match_repo.find_by_id(match_id)

        if match.player1_id != requester_id and match.player2_id != requester_id:
            raise PermissionError("You do not have access to this match")
        
        if not match:
            raise LookupError("Match not found")
        
        return match
    
    def get_current_round_status(self, match_id: int, requester_id: int) -> Dict:
        """Get the status of the current round."""
        match = self.get_match(match_id, requester_id, include_rounds=False)
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
        offset: int = 0,
        requester_id: Optional[int] = None,
    ) -> Dict:
        """Get match history for a player with statistics."""
        
        # Check friendship only if the requester is NOT the player
        if requester_id and requester_id != player_id:
            self._validate_friendship(requester_id, player_id)

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

    def _validate_friendship(self, player1_id: int, player2_id: int) -> None:
        """
        Validates if two players are friends using the Players Service.
        Raises PermissionError if not friends.
        Raises RuntimeError if service is unreachable.
        """
       
        if self._is_testing():
            pass

        players_url = current_app.config.get("PLAYERS_URL", "https://players:5000").rstrip("/")
        timeout = current_app.config.get("PLAYERS_REQUEST_TIMEOUT", 3)

        try:
            response = requests.post(
                f"{players_url}/internal/players/friendship/validation",
                json={"player1_id": player1_id, "player2_id": player2_id},
                timeout=timeout,
                verify=current_app.config.get("GAME_ENGINE_ENABLE_VERIFY", False)
            )
            
            if response.status_code != 200:
                current_app.logger.warning(
                    f"Friendship check failed with status {response.status_code}: {response.text}"
                )
                # Fail closed for security
                raise PermissionError("Could not verify friendship status")

            data = response.json()
            if not data.get("valid", False):
                raise PermissionError("You are not friends with this player")

        except requests.RequestException as e:
            current_app.logger.error(f"Failed to contact Players service: {e}")
            raise RuntimeError("Players service unavailable") from e
    
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
        category = random.choice(CARD_CATEGORIES) # nosec
        
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
    
    def _fetch_card_stats_from_ids(self, card_ids: List[int]) -> Dict:
        """
        Fetch full card objects using only their IDs.
        Uses mock data in testing mode, otherwise calls catalogue service.
        """
        # Use mock in testing mode
        if self._is_testing():
            from .mock_catalogue import mock_fetch_card_stats
            return mock_fetch_card_stats(card_ids)
        
        # Normal production flow
        base_url = current_app.config.get("CATALOGUE_URL", "https://catalogue:5000").rstrip("/")
        timeout = current_app.config.get("CATALOGUE_REQUEST_TIMEOUT", 3)

        payload = {"data": card_ids}

        try:
            response = requests.post(
                f"{base_url}/internal/cards/validation",
                json=payload,
                timeout=timeout,
                verify=current_app.config.get("GAME_ENGINE_ENABLE_VERIFY", False)
            )
        except requests.RequestException as exc:
            current_app.logger.error(f"Failed to reach catalogue service: {exc}")
            raise RuntimeError("Unable to reach catalogue service") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Catalogue service returned HTTP {response.status_code}")

        data = response.json().get("data")
        if not data or not isinstance(data, list):
            raise ValueError("Catalogue service returned invalid deck data")

        # Convert to dict: { card_id: card_data }
        mapped = {}
        for card in data:
            cid = int(card.get("id"))
            card["id"] = cid
            mapped[cid] = card
        return mapped
