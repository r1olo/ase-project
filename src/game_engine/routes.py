"""
Game engine HTTP routes for the card game

This blueprint handles all game logic through the service layer.
"""
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


# --- Core API Endpoints ---

@game_engine.get("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok"}), 200


@game_engine.post("/matches/create")
def create_match():
    """Create a new match with 2 player IDs."""
    payload = request.get_json(silent=True) or {}
    player1_id = payload.get("player1_id")
    player2_id = payload.get("player2_id")
    
    try:
        match = match_service.create_match(player1_id, player2_id)
        return jsonify(match.to_dict(include_rounds=False)), 201
    except Exception as e:
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
    player_id = int(get_jwt_identity())
    deck_cards = payload.get("data")

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
    player_id = int(get_jwt_identity())
    card_id = payload.get("card_id")
    
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
        '''
        TODO: View the match only if the player's id is part of it
        by retrieving the identity from the JWT token.
        '''
        result = match_service.get_current_round_status(match_id)
        current_app.logger.debug(f"Round status check for match {match_id}: {result['round_status']}")
        return jsonify(result), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>")
@jwt_required()
def get_match(match_id: int):
    """Get the match info (without rounds)."""
    try:
        '''
        TODO: View the match only if the player's id is part of it
        by retrieving the identity from the JWT token.
        '''
        match = match_service.get_match(match_id, include_rounds=False)
        current_app.logger.debug(f"Fetching match {match_id} info")
        return jsonify(match.to_dict(include_rounds=False)), 200
    except Exception as e:
        return _handle_service_error(e)


@game_engine.get("/matches/<int:match_id>/history")
@jwt_required()
def get_match_with_history(match_id: int):
    """
    Get the match info with all rounds.
    Uses eager loading to avoid N+1 queries.
    """
    try:
        '''
        TODO: View the match only if the player's id is part of it
        by retrieving the identity from the JWT token.
        '''
        match = match_service.get_match(match_id, include_rounds=True)
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


@game_engine.get("/players/<int:player_id>/history")
@jwt_required()
def get_player_history():
    """
    Get match history for a specific player with all rounds.
    
    Query params:
    - limit: Number of matches to return (default: 20, max: 100)
    - offset: Pagination offset (default: 0)
    - status: Filter by match status (optional: setup, in_progress, finished)
    """
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    status_filter = request.args.get('status', '').upper()
    player_id = int(get_jwt_identity())

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
