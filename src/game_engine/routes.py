"""
Game engine HTTP routes for the card game

This blueprint handles all game logic through the service layer.
"""
from flask import Blueprint, jsonify, request, current_app
from werkzeug.exceptions import NotFound

from common.extensions import db
from .services import MatchService
from .repositories import MoveRepository

game_engine = Blueprint("game_engine", __name__, url_prefix="/game")


# Initialize service
match_service = MatchService()


# --- Helper Functions ---

def _handle_service_error(e: Exception, default_status: int = 500):
    """Convert service exceptions to HTTP responses."""
    if isinstance(e, ValueError):
        current_app.logger.warning(f"Validation error: {e}")
        # Check if error is a dict with msg and code
        if isinstance(e.args[0], dict):
            return jsonify(e.args[0]), 400
        return jsonify({"msg": str(e)}), 400
    elif isinstance(e, LookupError):
        current_app.logger.warning(f"Not found: {e}")
        return jsonify({"msg": str(e)}), 404
    else:
        current_app.logger.error(f"Internal error: {e}", exc_info=True)
        return jsonify({"msg": "Internal server error"}), default_status


# --- Core API Endpoints ---

@game_engine.get("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@game_engine.post("/matches")
def create_match():
    """Create a new match with 2 player IDs."""
    payload = request.get_json(silent=True) or {}
    player1_id = payload.get("player1_id")
    player2_id = payload.get("player2_id")
    
    try:
        match = match_service.create_match(player1_id, player2_id)
        return jsonify(match.to_dict(include_moves=False)), 201
    except Exception as e:
        db.session.rollback()
        return _handle_service_error(e)


@game_engine.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck and fetches all card stats from the catalogue service.
    """
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    deck_card_ids = payload.get("deck")
    
    try:
        match = match_service.submit_deck(match_id, player_id, deck_card_ids)
        return jsonify(match.to_dict(include_moves=False)), 200
    except Exception as e:
        db.session.rollback()
        return _handle_service_error(e)


@game_engine.post("/matches/<int:match_id>/moves")
def submit_move(match_id: int):
    """Submit a move (a card) for the current round."""
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id")
    
    try:
        result = match_service.submit_move(match_id, player_id, card_id)
        return jsonify(result), 200
    except Exception as e:
        db.session.rollback()
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>/round")
def get_current_round_status(match_id: int):
    """Get the status of the current round, including the active category."""
    try:
        match = match_service.get_match(match_id)
        
        moves_this_round = MoveRepository.find_for_match_and_round(
            match_id, match.current_round
        )
        
        status = match_service.game_engine.get_round_status(len(moves_this_round))
        current_app.logger.debug(f"Round status check for match {match_id}: {status.value}")
        
        return jsonify({
            "match_id": match.id,
            "current_round": match.current_round,
            "current_round_category": match.current_round_category,
            "round_status": status.value,
            "moves_submitted_count": len(moves_this_round),
            "moves": [m.to_dict() for m in moves_this_round]
        }), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>")
def get_match(match_id: int):
    """Get the match info (without moves)."""
    try:
        match = match_service.get_match(match_id, include_moves=False)
        current_app.logger.debug(f"Fetching match {match_id} info")
        return jsonify(match.to_dict(include_moves=False)), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>/history")
def get_match_with_history(match_id: int):
    """
    Get the match info with all moves.
    Uses eager loading to avoid N+1 queries.
    """
    try:
        match = match_service.get_match(match_id, include_moves=True)
        current_app.logger.debug(f"Fetching match {match_id} history with {len(match.moves)} moves")
        return jsonify(match.to_dict(include_moves=True)), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/leaderboard")
def get_leaderboard():
    """
    Get the global leaderboard based on match wins.
    Returns top players ranked by number of wins.
    
    Query params:
    - limit: Number of players to return (default: 100, max: 500)
    - offset: Pagination offset (default: 0)
    """
    limit = min(int(request.args.get('limit', 100)), 500)
    offset = int(request.args.get('offset', 0))
    
    try:
        result = match_service.get_leaderboard(limit, offset)
        return jsonify(result), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/players/<int:player_id>/history")
def get_player_history(player_id: int):
    """
    Get match history for a specific player with all moves.
    
    Query params:
    - limit: Number of matches to return (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    - status: Filter by match status (optional: setup, in_progress, finished)
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    status_filter = request.args.get('status', '').upper()
    
    try:
        from .models import MatchStatus
        
        # Parse status filter
        status = None
        if status_filter and status_filter in [s.name for s in MatchStatus]:
            status = MatchStatus[status_filter]
        
        result = match_service.get_player_history(player_id, status, limit, offset)
        return jsonify(result), 200
    except Exception as e:
        return _handle_service_error(e)