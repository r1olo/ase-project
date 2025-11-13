"""
Game engine HTTP routes for the card game.

This blueprint handles all game logic: creating matches,
selecting decks, submitting moves, and processing rounds.
"""
import random
from flask import Blueprint, jsonify, request, current_app
from werkzeug.exceptions import NotFound

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

    if not isinstance(player1_id, int) or not isinstance(player2_id, int):
        return jsonify({"msg": "player1_id and player2_id must be integers"}), 400
    if player1_id == player2_id:
        return jsonify({"msg": "Player IDs must be different"}), 400

    match = Match(
        player1_id=player1_id,
        player2_id=player2_id,
    )
    db.session.add(match)
    db.session.commit()
    
    return jsonify(match.to_dict(include_moves=False)), 201

@bp.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck against the catalogue service.
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
    
    # --- TODO: Validate deck against Catalogue Microservice ---
    # catalogue_url = os.environ.get("CATALOGUE_SERVICE_URL")
    # try:
    #     response = requests.post(f"{catalogue_url}/cards/validate-ids", json={"card_ids": deck})
    #     response.raise_for_status()
    #     if not response.json().get("valid"):
    #         return jsonify({"msg": "Invalid deck"}), 400
    # except requests.exceptions.RequestException as e:
    #     return jsonify({"msg": "Catalogue service unavailable"}), 503
    # --- End TODO ---

    if player_id == match.player1_id:
        match.player1_deck = deck
    elif player_id == match.player2_id:
        match.player2_deck = deck
    else:
        return jsonify({"msg": "Player is not part of this match"}), 403

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
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id")

    if not isinstance(player_id, int) or not isinstance(card_id, str):
        return jsonify({"msg": "player_id (int) and card_id (str) are required"}), 400

    # We use a transaction and lock to handle concurrency.
    # The 'with_for_update' locks the match row until the 'try'
    # block is finished and a commit/rollback happens.
    try:
        match = db.session.scalars(
            db.select(Match).filter_by(id=match_id).with_for_update()
        ).first()
        
        if not match:
            raise NotFound(description="Match not found")

        # --- Validation Block ---
        if match.status != MatchStatus.IN_PROGRESS:
            return jsonify({"msg": "Match is not in progress"}), 400
        if player_id not in [match.player1_id, match.player2_id]:
            return jsonify({"msg": "Player is not part of this match"}), 403

        player_deck = match.player1_deck if player_id == match.player1_id else match.player2_deck
        if not player_deck:
            return jsonify({"msg": "Player deck not found or not set"}), 400
        if card_id not in player_deck:
            return jsonify({"msg": f"Card {card_id} is not in the player's deck"}), 400
        
        # Get only the moves for the current round
        moves_this_round = db.session.scalars(
            db.select(Move).filter_by(
                match_id=match_id,
                round_number=match.current_round
            )
        ).all()

        # Check if this player has already moved this round
        if player_id in [m.player_id for m in moves_this_round]:
            return jsonify({"msg": "Player has already submitted a move for this round"}), 409

        # Save the New Move
        move = Move(
            match=match,
            player_id=player_id,
            round_number=match.current_round,
            card_id=card_id
        )
        db.session.add(move)

        if len(moves_this_round) == 0:
            # This is the first move of the round.
            # Commit the move and release the lock.
            db.session.commit()
            return jsonify({
                "status": "WAITING_FOR_OPPONENT",
                "move_submitted": move.to_dict()
            }), 200

        elif len(moves_this_round) == 1:
            # This is the second move. Process the round.
            # We are still holding the lock.
            
            move_p1 = moves_this_round[0]
            move_p2 = move # The new move we just created
            category = match.current_round_category

            # --- TODO: Call Catalogue Microservice ---
            # catalogue_url = os.environ.get("CATALOGUE_SERVICE_URL")
            # response = requests.post(f"{catalogue_url}/cards/batch-lookup", ...)
            # card_stats_map = response.json()
            card_stats_map = {
                move_p1.card_id: {"economy": 10, "food": 5, "environment": 7, "special": 0, "total": 22.0},
                move_p2.card_id: {"economy": 8, "food": 12, "environment": 6, "special": 2, "total": 28.0}
            }

            card1_stats = card_stats_map.get(move_p1.card_id)
            card2_stats = card_stats_map.get(move_p2.card_id)

            if not card1_stats or not card2_stats:
                raise Exception("Card stats not found in catalogue")

            score1 = card1_stats[category]
            score2 = card2_stats[category]
            
            round_winner_id = None
            if score1 > score2:
                round_winner_id = move_p1.player_id
            elif score2 > score1:
                round_winner_id = move_p2.player_id
            
            if round_winner_id == match.player1_id:
                match.player1_score += 1
            elif round_winner_id == match.player2_id:
                match.player2_score += 1

            # End Game or Advance Round
            if match.current_round >= MAX_ROUNDS:
                match.status = MatchStatus.FINISHED
                if match.player1_score > match.player2_score:
                    match.winner_id = match.player1_id
                elif match.player2_score > match.player1_score:
                    match.winner_id = match.player2_id
                match.current_round_category = None
            else:
                match.current_round += 1
                match.current_round_category = random.choice(CARD_CATEGORIES)

            # Commit all changes (new move, match update) at once.
            db.session.commit()
            
            return jsonify({
                "status": "ROUND_PROCESSED",
                "round_winner_id": round_winner_id,
                "moves": [move_p1.to_dict(), move_p2.to_dict()],
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
        # If anything fails (catalogue call, logic error), roll back.
        db.session.rollback()
        current_app.logger.error(f"Error in submit_move: {e}")
        return jsonify({"msg": "Internal server error"}), 500

    # This line should not be reachable
    return jsonify({"msg": "Internal server error"}), 500


@bp.get("/matches/<int:match_id>/round")
def get_current_round_status(match_id: int):
    """
    Get the status of the current round, including the active category.
    """
    match = _match_or_404(match_id)
    
    # Get only the moves for this round.
    moves_this_round = db.session.scalars(
        db.select(Move).filter_by(
            match_id=match_id,
            round_number=match.current_round
        )
    ).all()

    status_text = "WAITING_FOR_BOTH_PLAYERS"
    if len(moves_this_round) == 1:
        status_text = "WAITING_FOR_ONE_PLAYER"
    elif len(moves_this_round) == 2:
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
    """
    match = _match_or_404(match_id)
    return jsonify(match.to_dict(include_moves=False))


@bp.get("/matches/<int:match_id>/history")
def get_match_with_history(match_id: int):
    """
    Get the match info with all moves.
    """
    match = _match_or_404(match_id)
    return jsonify(match.to_dict(include_moves=True))