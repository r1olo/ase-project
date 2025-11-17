"""
Game engine HTTP routes for the card game.

This blueprint handles all game logic: creating matches,
selecting decks, submitting moves, and processing rounds.
"""
import random
from flask import Blueprint, jsonify, request, current_app
from werkzeug.exceptions import NotFound
from sqlalchemy.orm import joinedload

from common.extensions import db 

from .models import Match, Move, MatchStatus, CARD_CATEGORIES
from .game_engine import GameEngine, MoveSubmissionStatus, RoundStatus

bp = Blueprint("game_engine", __name__, url_prefix="/game")



# --- Helper Functions ---

def _match_or_404(match_id: int) -> Match:
    """Gets a Match by its integer ID or raises a 404."""
    match = db.session.get(Match, match_id)
    if not match:
        current_app.logger.warning(f"Match {match_id} not found")
        raise NotFound(description="Match not found")
    return match


# --- Core API Endpoints ---

@bp.get("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@bp.post("/matches")
def create_match():
    """
    Create a new match with 2 player IDs.
    """
    payload = request.get_json(silent=True) or {}
    player1_id = payload.get("player1_id")
    player2_id = payload.get("player2_id")

    # Validate using GameEngine
    is_valid, error_msg = GameEngine.validate_match_creation(player1_id, player2_id)
    if not is_valid:
        current_app.logger.warning(f"Invalid match creation: {error_msg}")
        return jsonify({"msg": error_msg}), 400

    try:
        match = Match(
            player1_id=player1_id,
            player2_id=player2_id,
        )
        db.session.add(match)
        db.session.commit()
        
        current_app.logger.info(f"Match {match.id} created between players {player1_id} and {player2_id}")
        return jsonify(match.to_dict(include_moves=False)), 201
    
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating match: {e}", exc_info=True)
        return jsonify({"msg": "Internal server error"}), 500


@bp.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck and fetches all card stats from the catalogue service.
    """
    try:
        match = _match_or_404(match_id)
        
        payload = request.get_json(silent=True) or {}
        player_id = payload.get("player_id")
        deck_card_ids = payload.get("deck")

        # Validate using GameEngine
        is_valid, error_msg = GameEngine.validate_deck_submission(deck_card_ids, player_id, match)
        if not is_valid:
            current_app.logger.warning(f"Invalid deck submission for match {match_id}: {error_msg}")
            return jsonify({"msg": error_msg}), 400
        
        """
        Fetch card stats from the catalogue service.
        
        TODO: Implement actual API call to catalogue service.
        Currently returns mock data.
        
        Returns:
            Dictionary mapping card_id to stats dictionary
        """
        # --- TODO: Call Catalogue Microservice ---
        # catalogue_url = os.environ.get("CATALOGUE_SERVICE_URL")
        # try:
        #     response = requests.post(
        #         f"{catalogue_url}/cards/batch-lookup", 
        #         json={"card_ids": deck_card_ids}
        #     )
        #     response.raise_for_status()
        #     return response.json() 
        # except requests.exceptions.RequestException as e:
        #     current_app.logger.error(f"Catalogue service error: {e}")
        #     raise ValidationError("Catalogue service unavailable")
        
        # --- MOCK DATA (Remove when TODO is implemented) ---
        deck_stats_map = {}
        for card_id in deck_card_ids:
            deck_stats_map[card_id] = {
                "economy": random.randint(5, 15), 
                "food": random.randint(5, 15), 
                "environment": random.randint(5, 15), 
                "special": random.randint(0, 5), 
                "total": random.uniform(20.0, 40.0)
            }
        

        # Assign deck to the correct player
        if player_id == match.player1_id:
            match.player1_deck = deck_stats_map
            current_app.logger.info(f"Player 1 (ID: {player_id}) deck set for match {match_id} with {len(deck_card_ids)} cards")
        else:  # player_id == match.player2_id
            match.player2_deck = deck_stats_map
            current_app.logger.info(f"Player 2 (ID: {player_id}) deck set for match {match_id} with {len(deck_card_ids)} cards")

        # Check if match should start using GameEngine
        if GameEngine.should_start_match(match):
            match.status = MatchStatus.IN_PROGRESS
            current_app.logger.info(f"Match {match_id} starting - both decks submitted")
            
        db.session.commit()
        return jsonify(match.to_dict(include_moves=False))
    
    except NotFound as e:
        return jsonify({"msg": str(e)}), 404
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in choose_deck for match {match_id}: {e}", exc_info=True)
        return jsonify({"msg": "Internal server error"}), 500


@bp.post("/matches/<int:match_id>/moves")
def submit_move(match_id: int):
    """
    Submit a move (a card) for the current round.
    """
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id")

    try:
        # Lock match row to avoid race conditions
        match = db.session.scalars(
            db.select(Match).filter_by(id=match_id).with_for_update()
        ).first()

        if not match:
            current_app.logger.warning(f"Match {match_id} not found for move submission")
            raise NotFound("Match not found")

        # MOVES FOR VALIDATION
        moves_this_round = db.session.scalars(
            db.select(Move).filter_by(
                match_id=match_id,
                round_number=match.current_round
            )
        ).all()

        all_player_moves = db.session.scalars(
            db.select(Move).filter_by(
                match_id=match_id,
                player_id=player_id
            )
        ).all()

        # VALIDATE MOVE (returns {"msg": "...", "code": "..."} on fail)
        is_valid, err = GameEngine.validate_move_submission(
            player_id, card_id, match, moves_this_round, all_player_moves
        )

        if not is_valid:
            current_app.logger.warning(
                f"Invalid move for match {match_id}: {err['msg']} ({err['code']})"
            )
            return jsonify({
                "msg": err["msg"],
                "code": err["code"]
            }), 400

        # CREATE MOVE
        move = Move(
            match=match,
            player_id=player_id,
            round_number=match.current_round,
            card_id=card_id
        )
        db.session.add(move)
        current_app.logger.info(
            f"Move submitted: Player {player_id} played {card_id} in round {match.current_round}"
        )

        # Append now-inserted move so we have both moves in memory
        moves_this_round.append(move)

        # FIRST OR SECOND MOVE?
        is_second_move = GameEngine.should_process_round(moves_this_round)

        # --- FIRST MOVE ---
        if not is_second_move:
            db.session.commit()
            current_app.logger.info(
                f"First move of round {match.current_round} submitted, waiting for opponent."
            )
            return jsonify({
                "status": MoveSubmissionStatus.WAITING_FOR_OPPONENT.value,
                "move_submitted": move.to_dict()
            }), 200

        # --- SECOND MOVE ---
        try:
            p1_move = next(m for m in moves_this_round if m.player_id == match.player1_id)
            p2_move = next(m for m in moves_this_round if m.player_id == match.player2_id)
        except StopIteration:
            raise Exception("Required moves for both players not found.")

        category = match.current_round_category
        current_app.logger.info(
            f"Processing round {match.current_round} for match {match_id}, category: {category}"
        )

        # SCORES
        try:
            p1_score, p2_score = GameEngine.calculate_round_scores(match, p1_move, p2_move, category)
        except KeyError as e:
            raise Exception(f"Missing card stats during round scoring: {e}")

        # ROUND WINNER
        round_winner_id, is_draw = GameEngine.calculate_round_winner(
            p1_score, p2_score, match.player1_id, match.player2_id
        )

        # UPDATE SCOREBOARD
        GameEngine.update_match_scores(match, round_winner_id)

        # MATCH END CHECK
        if GameEngine.should_end_match(match):
            GameEngine.finalize_match(match)
            current_app.logger.info(
                f"Match {match_id} finished. Winner={match.winner_id}"
            )
        else:
            GameEngine.advance_to_next_round(match)
            current_app.logger.info(
                f"Advancing to round {match.current_round}, next category={match.current_round_category}"
            )

        db.session.commit()

        return jsonify({
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
        }), 200

    except NotFound as e:
        return jsonify({"msg": str(e)}), 404

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(
            f"Error in submit_move for match {match_id}: {e}", exc_info=True
        )
        return jsonify({"msg": "Internal server error"}), 500


@bp.get("/matches/<int:match_id>/round")
def get_current_round_status(match_id: int):
    """
    Get the status of the current round, including the active category.
    """
    match = _match_or_404(match_id)
    
    moves_this_round = db.session.scalars(
        db.select(Move).filter_by(
            match_id=match_id,
            round_number=match.current_round
        )
    ).all()

    # Get status using GameEngine
    status = GameEngine.get_round_status(len(moves_this_round))
    current_app.logger.debug(f"Round status check for match {match_id}: {status.value}")

    return jsonify({
        "match_id": match.id,
        "current_round": match.current_round,
        "current_round_category": match.current_round_category,
        "round_status": status.value,
        "moves_submitted_count": len(moves_this_round),
        "moves": [m.to_dict() for m in moves_this_round]
    })


@bp.get("/matches/<int:match_id>")
def get_match(match_id: int):
    """
    Get the match info (without moves).
    """
    match = _match_or_404(match_id)
    current_app.logger.debug(f"Fetching match {match_id} info")
    return jsonify(match.to_dict(include_moves=False))


@bp.get("/matches/<int:match_id>/history")
def get_match_with_history(match_id: int):
    """
    Get the match info with all moves.
    Uses eager loading to avoid N+1 queries.
    """
    # Use joinedload to fetch moves in a single query
    match = db.session.scalars(
        db.select(Match)
        .options(joinedload(Match.moves))
        .filter_by(id=match_id)
    ).first()
    
    if not match:
        current_app.logger.warning(f"Match {match_id} not found for history request")
        raise NotFound(description="Match not found")
    
    current_app.logger.debug(f"Fetching match {match_id} history with {len(match.moves)} moves")
    return jsonify(match.to_dict(include_moves=True))