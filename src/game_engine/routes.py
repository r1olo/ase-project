"""
Game engine HTTP routes for the card game.

This blueprint handles all game logic: creating matches,
selecting decks, submitting moves, and processing rounds.
"""
import random
from flask import Blueprint, jsonify, request, current_app
from werkzeug.exceptions import NotFound
from sqlalchemy.exc import IntegrityError

from common.extensions import db 
from .models import Match, Move, MatchStatus, CARD_CATEGORIES

bp = Blueprint("game_engine", __name__, url_prefix="/game")

# --- Constants ---

# Define the total number of rounds before a game ends.
MAX_ROUNDS = 10 

# --- Helper Functions ---

def _match_or_404(match_id: int) -> Match:
    """Gets a Match by its integer ID or raises a 404."""
    match = db.session.get(Match, match_id)
    if not match:
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

    # Validate input
    if not isinstance(player1_id, int) or not isinstance(player2_id, int):
        return jsonify({"msg": "player1_id and player2_id must be integers"}), 400
    if player1_id == player2_id:
        return jsonify({"msg": "Player IDs must be different"}), 400

    # Create match
    # The Match __init__ method now handles setting the first round's category.
    match = Match(
        player1_id=player1_id,
        player2_id=player2_id,
    )
    db.session.add(match)
    db.session.commit()
    
    # Return the new match (without moves)
    return jsonify(match.to_dict(include_moves=False)), 201

@bp.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck against the catalogue service.
    """
    match = _match_or_404(match_id)

    # Check game state
    if match.status != MatchStatus.SETUP:
        return jsonify({"msg": "Decks can only be chosen during SETUP"}), 400

    # Validate payload
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    deck = payload.get("deck") # Expects a list of card IDs

    if not isinstance(player_id, int) or not isinstance(deck, list):
        return jsonify({"msg": "player_id (int) and deck (list) are required"}), 400
    if not deck:
         return jsonify({"msg": "Deck cannot be empty"}), 400
    
    # TODO: Validate deck against Catalogue Microservice.

    # Assign the deck to the correct player
    if player_id == match.player1_id:
        match.player1_deck = deck
    elif player_id == match.player2_id:
        match.player2_deck = deck
    else:
        return jsonify({"msg": "Player is not part of this match"}), 403

    # If both decks are set, start the game
    if match.player1_deck is not None and match.player2_deck is not None:
        match.status = MatchStatus.IN_PROGRESS
        
    db.session.commit()
    return jsonify(match.to_dict(include_moves=False))

@bp.post("/matches/<int:match_id>/moves")
def submit_move(match_id: int):
    """
    Submit a move (a card) for the current round.
    This is the core game logic endpoint.
    """

    # Get and validate payload
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id")

    if not isinstance(player_id, int) or not isinstance(card_id, str):
        return jsonify({"msg": "player_id (int) and card_id (str) are required"}), 400

    # Get the match and LOCK the row for update.
    # This is critical to prevent race conditions.
    match = db.session.scalars(
        db.select(Match).filter_by(id=match_id).with_for_update()
    ).first()
    if not match:
        raise NotFound(description="Match not found")

    # Validate game state and player
    if match.status != MatchStatus.IN_PROGRESS:
        return jsonify({"msg": "Match is not in progress"}), 400
    if player_id not in [match.player1_id, match.player2_id]:
        return jsonify({"msg": "Player is not part of this match"}), 403

    # Validate the card is in the player's deck
    player_deck = match.player1_deck if player_id == match.player1_id else match.player2_deck
    if not player_deck:
        return jsonify({"msg": "Player deck not found or not set"}), 400
    if card_id not in player_deck:
        return jsonify({"msg": f"Card {card_id} is not in the player's deck"}), 400
    
    # TODO: Check if card has already been played by this player in a previous round.
    # This requires adding logic to remove cards from the deck, or checking
    # the 'moves' table. For now, we assume any card in the deck is playable.
    
    # Create and save the move
    move = Move(
        match=match,
        player_id=player_id,
        round_number=match.current_round,
        card_id=card_id
    )
    db.session.add(move)

    try:
        # This commit will fail if the UniqueConstraint is violated
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "Player has already submitted a move for this round"}), 409

    # Check if the round is ready to be processed
    moves_this_round = [m for m in match.moves if m.round_number == match.current_round]

    if len(moves_this_round) == 1:
        # We are still waiting for the other player.
        return jsonify({
            "status": "WAITING_FOR_OPPONENT",
            "move_submitted": move.to_dict()
        }), 200

    if len(moves_this_round) == 2:
        # Both players have moved. Process the round.
        move_p1 = moves_this_round[0]
        move_p2 = moves_this_round[1]
        category = match.current_round_category

        # TODO: Call Catalogue Microservice to get card stats
        card_stats_map = {
            move_p1.card_id: {"economy": 10, "food": 5, "environment": 7, "special": 0, "total": 22.0},
            move_p2.card_id: {"economy": 8, "food": 12, "environment": 6, "special": 2, "total": 28.0}
        }
        
        # Determine round winner
        try:
            card_p1_stats = card_stats_map[move_p1.card_id]
            card_p2_stats = card_stats_map[move_p2.card_id]
            
            score_p1 = card_p1_stats[category]
            score_p2 = card_p2_stats[category]
        except KeyError:
            # This handles bad data from the catalogue or a mismatch
            # in category names.
            return jsonify({"msg": f"Invalid category '{category}' or bad card data"}), 500

        # Check who won the round
        round_winner_id = None
        if score_p1 > score_p2:
            round_winner_id = move_p1.player_id
            match.player1_score += 1
        elif score_p2 > score_p1:
            round_winner_id = move_p2.player_id
            match.player2_score += 1

        # Prepare for Next Round or End Game
        if match.current_round >= MAX_ROUNDS:
            match.status = MatchStatus.FINISHED
            if match.player1_score > match.player2_score:
                match.winner_id = match.player1_id
            elif match.player2_score > match.player1_score:
                match.winner_id = match.player2_id
            match.current_round_category = None # Game over
        else:
            # Advance to the next round and pick a new category
            match.current_round += 1
            match.current_round_category = random.choice(CARD_CATEGORIES)

        db.session.commit()
        
        # Return the result
        return jsonify({
            "status": "ROUND_PROCESSED",
            "round_winner_id": round_winner_id,
            "moves": [m.to_dict() for m in moves_this_round],
            "scores": {
                match.player1_id: match.player1_score,
                match.player2_id: match.player2_score
            },
            "next_round": match.current_round,
            "next_category": match.current_round_category,
            "game_status": match.status.name
        }), 200

    # This line should not be reachable
    return jsonify({"msg": "Internal server error processing moves"}), 500


@bp.get("/matches/<int:match_id>/round")
def get_current_round_status(match_id: int):
    """
    Get the status of the current round, including the active category.
    """
    match = _match_or_404(match_id)
    
    # Find moves submitted *for the current round*
    moves_this_round = [m for m in match.moves if m.round_number == match.current_round]

    status_text = "WAITING_FOR_BOTH_PLAYERS"
    if len(moves_this_round) == 1:
        status_text = "WAITING_FOR_ONE_PLAYER"
    elif len(moves_this_round) == 2:
        # This state is transient, as submit_move will process it
        status_text = "ROUND_COMPLETE_OR_PROCESSING"

    return jsonify({
        "match_id": match.id,
        "current_round": match.current_round,
        "current_round_category": match.current_round_category,
        "round_status": status_text,
        "moves_submitted_count": len(moves_this_round),
        "moves": [m.to_dict() for m in moves_this_round]
    })


@bp.get("/matches/<int:match_id>")
def get_match(match_id: int):
    """
    Get the match info (without moves).
    This is the lightweight endpoint for a general status check.
    """
    match = _match_or_404(match_id)
    # include_moves=False is the default, but we are explicit
    return jsonify(match.to_dict(include_moves=False))


@bp.get("/matches/<int:match_id>/history")
def get_match_with_history(match_id: int):
    """
    Get the match info with all moves.
    This is the heavyweight endpoint for a full game replay.
    """
    match = _match_or_404(match_id)
    # Explicitly asks for the full move history
    return jsonify(match.to_dict(include_moves=True))