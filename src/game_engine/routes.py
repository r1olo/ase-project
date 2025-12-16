"""
Game engine HTTP routes for the card game

This blueprint handles all game logic through the service layer.
"""
import re
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import get_jwt_identity, jwt_required

from common.extensions import db
from .services import MatchService

game_engine = Blueprint("game_engine", __name__)


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
    elif isinstance(e, RuntimeError):
        current_app.logger.error(f"Service unavailable: {e}")
        return jsonify({"msg": str(e)}), 503
    elif isinstance(e, LookupError):
        current_app.logger.warning(f"Not found: {e}")
        return jsonify({"msg": str(e)}), 404
    else:
        current_app.logger.error(f"Internal error: {e}", exc_info=True)
        return jsonify({"msg": "Internal server error"}), default_status
    
# --- Input Validation Helpers ---

def _validate_id(value, field_name: str) -> int:
    """Strictly validates that input is a positive integer."""
    try:
        if value is None:
            raise ValueError(f"Missing required field: {field_name}")
        
        # Check strictly for int type or a digit-only string (no floats)
        if isinstance(value, str) and not value.isdigit():
            raise ValueError(f"Invalid format for {field_name}")
            
        val = int(value)
        if val < 0:
            raise ValueError(f"{field_name} cannot be negative")
        return val
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer for {field_name}")

def _validate_ids_list(values, field_name: str) -> list[int]:
    """Validates a list of integers."""
    if not isinstance(values, list):
        raise ValueError(f"{field_name} must be a list")
    return [_validate_id(v, f"{field_name} item") for v in values]

def _sanitize_string(value, field_name: str) -> str:
    """Uses Regex to ensure only safe alphanumeric characters."""
    if not value:
        return None
    s_val = str(value).strip()
    
    # Strip surrounding quotes if present
    if s_val.startswith('"') and s_val.endswith('"'):
        s_val = s_val[1:-1]
    if s_val.startswith("'") and s_val.endswith("'"):
        s_val = s_val[1:-1]
    
    # Allow only A-Z, 0-9, and underscores
    if not re.match(r'^[a-zA-Z0-9_]+$', s_val):
        raise ValueError(f"Invalid characters in {field_name}")
    return s_val


# --- Core API Endpoints ---

@game_engine.get("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@game_engine.post("/internal/matches/create")
def create_match():
    """Create a new match with 2 player IDs."""
    try:
        current_app.logger.info("Received create match request")
        payload = request.get_json(silent=True) or {}
        current_app.logger.info(f"Payload: {payload}")
        
        # Get the payload and sanitize
        player1_id = _validate_id(payload.get("player1_id"), "player1_id")
        player2_id = _validate_id(payload.get("player2_id"), "player2_id")

        current_app.logger.info(f"Creating match: p1={player1_id}, p2={player2_id}")
        match = match_service.create_match(player1_id, player2_id)
        
        current_app.logger.info(f"Match created: {match.id}")
        result = match.to_dict(include_rounds=False)
        current_app.logger.info(f"Returning: {result}")
        
        return jsonify(result), 201
    except Exception as e:
        current_app.logger.error(f"Error creating match: {e}", exc_info=True)
        db.session.rollback()
        return _handle_service_error(e)


@game_engine.post("/matches/<int:match_id>/deck")
@jwt_required()
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck.
    """
    payload = request.get_json(silent=True) or {}

    # Sanitize inputs
    match_id = _validate_id(match_id, "match_id")
    player_id = _validate_id(get_jwt_identity(), "auth_token")
    deck_cards = _validate_ids_list(payload.get("data"), "deck_data")

    try:
        match = match_service.submit_deck(match_id, player_id, deck_cards)
        return jsonify(match.to_dict(include_rounds=False)), 200
    except Exception as e:
        db.session.rollback()
        return _handle_service_error(e)



@game_engine.post("/matches/<int:match_id>/moves/<int:round_number>")
@jwt_required()
def submit_move(match_id: int, round_number: int):
    """Submit a move (a card) for the current round."""
    payload = request.get_json(silent=True) or {}

    # Sanitize inputs
    match_id = _validate_id(match_id, "match_id")
    round_number = _validate_id(round_number, "round_number")
    
    player_id = _validate_id(get_jwt_identity(), "auth_token")
    card_id = _validate_id(payload.get("card_id"), "card_id")
    
    try:
        result = match_service.submit_move(match_id, player_id, card_id, round_number)
        return jsonify(result), 200
    except Exception as e:
        db.session.rollback()
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>/round")
@jwt_required()
def get_current_round_status(match_id: int):
    """Get the status of the current round, including the active category."""
    try:
        # Sanitize inputs
        requester_id = _validate_id(get_jwt_identity(), "auth_token")
        match_id = _validate_id(match_id, "match_id")

        result = match_service.get_current_round_status(match_id, requester_id)
        current_app.logger.debug(f"Round status check for match {match_id}: {result['round_status']}")
        return jsonify(result), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>")
@jwt_required()
def get_match(match_id: int):
    """Get the match info (without rounds)."""
    try:
        # Sanitize inputs
        requester_id = _validate_id(get_jwt_identity(), "auth_token")
        match_id = _validate_id(match_id, "match_id")

        match = match_service.get_match(match_id, requester_id, include_rounds=False)
        current_app.logger.debug(f"Fetching match {match_id} info")
        return jsonify(match.to_dict(include_rounds=False)), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>/history")
@jwt_required()
def get_match_with_rounds(match_id: int):
    """
    Get the match info with all rounds.
    Uses eager loading to avoid N+1 queries.
    """
    try:
        # Sanitize inputs
        requester_id = _validate_id(get_jwt_identity(), "auth_token")
        match_id = _validate_id(match_id, "match_id")

        match = match_service.get_match(match_id, requester_id, include_rounds=True)
        current_app.logger.debug(f"Fetching match {match_id} history with {len(match.rounds)} rounds")
        return jsonify(match.to_dict(include_rounds=True)), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/leaderboard")
@jwt_required()
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


@game_engine.get("/matches/history/<int:player_id>")
@jwt_required()
def get_player_history(player_id: int):
    """
    Get match history for a specific player with all rounds.
    
    Query params:
    - limit: Number of matches to return (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    - status: Filter by match status (optional: setup, in_progress, finished)
    """

    try:
        # Sanitize inputs
        player_id = _validate_id(player_id, "player_id")
        requester_id = _validate_id(get_jwt_identity(), "auth_token")

        limit = _validate_id(request.args.get('limit', 20), "limit")
        offset = _validate_id(request.args.get('offset', 0), "offset")
        
        raw_status = request.args.get('status', '')
        status_filter = _sanitize_string(raw_status, "status")

        from .models import MatchStatus
        
        # Parse status filter
        status = None
        if status_filter:
            status_key = status_filter.upper()
            if status_key in [s.name for s in MatchStatus]:
                status = MatchStatus[status_key]
        
        result = match_service.get_player_history(player_id, status, limit, offset, requester_id)
        return jsonify(result), 200
    except Exception as e:
        return _handle_service_error(e)
