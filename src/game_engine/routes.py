"""Game engine HTTP routes for the card game."""

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import NotFound
from sqlalchemy.exc import IntegrityError

from common.extensions import db 
from .models import Match, Move, MatchStatus 


bp = Blueprint("game_engine", __name__, url_prefix="/game")


def _match_or_404(match_id: int) -> Match:
    """Gets a Match by its integer ID or raises a 404."""
    match = db.session.get(Match, match_id)
    if not match:
        raise NotFound(description="Match not found")
    return match


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

    # Basic validation
    if not isinstance(player1_id, int) or not isinstance(player2_id, int):
        return jsonify({"msg": "player1_id and player2_id must be integers"}), 400
    if player1_id == player2_id:
        return jsonify({"msg": "Player IDs must be different"}), 400

    match = Match(
        player1_id=player1_id,
        player2_id=player2_id,
        # status and current_round use model defaults
    )
    db.session.add(match)
    db.session.commit()
    
    # Return the match, but not its (empty) move list
    return jsonify(match.to_dict(include_moves=False)), 201


@bp.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Choose a subset of cards (deck).
    """
    match = _match_or_404(match_id)

    if match.status != MatchStatus.SETUP:
        return jsonify({"msg": "Decks can only be chosen during SETUP"}), 400

    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    deck = payload.get("deck") # Expects a list of card IDs

    if not isinstance(player_id, int) or not isinstance(deck, list):
        return jsonify({"msg": "player_id (int) and deck (list) are required"}), 400

    if not deck:
         return jsonify({"msg": "Deck cannot be empty"}), 400
    
    # TODO: Add deck validation logic

    # Assign the deck to the correct player
    if player_id == match.player1_id:
        match.player1_deck = deck
    elif player_id == match.player2_id:
        match.player2_deck = deck
    else:
        return jsonify({"msg": "Player is not part of this match"}), 403

    # Check if the game is ready to start
    if match.player1_deck is not None and match.player2_deck is not None:
        match.status = MatchStatus.IN_PROGRESS
        
    db.session.commit()
    return jsonify(match.to_dict(include_moves=False))


@bp.post("/matches/<int:match_id>/moves")
def submit_move(match_id: int):
    """
    Submit a move for the current round.
    Handles the core game logic of waiting and processing.
    """
    # Get and validate payload
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id")

    if not isinstance(player_id, int) or not isinstance(card_id, str):
        return jsonify({"msg": "player_id (int) and card_id (str) are required"}), 400

    # Get the match and LOCK the row for update
    # This prevents two moves from being processed simultaneously
    match = db.session.scalars(
        db.select(Match).filter_by(id=match_id).with_for_update()
    ).first()
    if not match:
        raise NotFound(description="Match not found")

    # Validate game state
    if match.status != MatchStatus.IN_PROGRESS:
        return jsonify({"msg": "Match is not in progress"}), 400
    if player_id not in [match.player1_id, match.player2_id]:
        return jsonify({"msg": "Player is not part of this match"}), 403

    player_deck = None
    if player_id == match.player1_id:
        player_deck = match.player1_deck
    else:
        player_deck = match.player2_deck

    if not player_deck:
        # This should never happen if the 'choose_deck' logic is correct
        return jsonify({"msg": "Player deck not found or not set"}), 400

    # Check if the card is in the player's deck
    if card_id not in player_deck:
        return jsonify({"msg": f"Card {card_id} is not in the player's deck"}), 400
    
    # Create and save the move
    move = Move(
        match=match, # Use the relationship
        player_id=player_id,
        round_number=match.current_round,
        card_id=card_id
    )
    db.session.add(move)

    try:
        db.session.commit()
    except IntegrityError:
        # This triggers if the UniqueConstraint fails
        db.session.rollback()
        return jsonify({"msg": "Player has already submitted a move for this round"}), 409

    # Check round status and process
    # Re-fetch moves from the relationship (which is now updated)
    moves_this_round = [m for m in match.moves if m.round_number == match.current_round]

    if len(moves_this_round) == 1:
        # Waiting for the other player
        return jsonify({
            "status": "WAITING_FOR_OPPONENT",
            "move_submitted": move.to_dict()
        }), 200

    if len(moves_this_round) == 2:
        # TODO: Implement game logic to determine round winner
        match.current_round += 1
        db.session.commit()
        
        return jsonify({
            "status": "ROUND_PROCESSED",
            "moves": [m.to_dict() for m in moves_this_round],
            "next_round": match.current_round
        }), 200

    # This should not be reachable
    return jsonify({"msg": "Internal server error processing moves"}), 500


@bp.get("/matches/<int:match_id>/round")
def get_current_round_status(match_id: int):
    """
    Get the status of the current round.
    """
    match = _match_or_404(match_id)
    
    # Find moves submitted for the current round
    moves_this_round = [m for m in match.moves if m.round_number == match.current_round]

    status_text = "WAITING_FOR_BOTH_PLAYERS"
    if len(moves_this_round) == 1:
        status_text = "WAITING_FOR_ONE_PLAYER"
    elif len(moves_this_round) == 2:
        status_text = "ROUND_COMPLETE_OR_PROCESSING"

    return jsonify({
        "match_id": match.id,
        "current_round": match.current_round,
        "round_status": status_text,
        "moves_submitted_count": len(moves_this_round),
        "moves": [m.to_dict() for m in moves_this_round]
    })


@bp.get("/matches/<int:match_id>")
def get_match(match_id: int):
    """
    Get the match info (without moves).
    """
    match = _match_or_404(match_id)
    # Uses the flag to minimize overhead.
    return jsonify(match.to_dict(include_moves=False))


@bp.get("/matches/<int:match_id>/history")
def get_match_with_history(match_id: int):
    """
    Get the match info with all moves.
    """
    match = _match_or_404(match_id)
    # Explicitly asks for the full move history.
    return jsonify(match.to_dict(include_moves=True))