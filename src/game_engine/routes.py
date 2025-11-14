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

    try:
        match = Match(
            player1_id=player1_id,
            player2_id=player2_id,
        )
        db.session.add(match)
        db.session.commit()
        
        return jsonify(match.to_dict(include_moves=False)), 201
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating match: {e}")
        return jsonify({"msg": "Internal server error"}), 500

@bp.post("/matches/<int:match_id>/deck")
def choose_deck(match_id: int):
    """
    Endpoint for a player to submit their chosen deck (subset of cards).
    Validates the deck and *fetches all card stats* from the catalogue service.
    """
    try:
        match = _match_or_404(match_id)

        if match.status != MatchStatus.SETUP:
            return jsonify({"msg": "Decks can only be chosen during SETUP"}), 400

        payload = request.get_json(silent=True) or {}
        player_id = payload.get("player_id")
        deck_card_ids = payload.get("deck") # Expects a *list* of card IDs

        if not isinstance(player_id, int) or not isinstance(deck_card_ids, list):
            return jsonify({"msg": "player_id (int) and deck (list) are required"}), 400
        if not deck_card_ids:
            return jsonify({"msg": "Deck cannot be empty"}), 400
        
        # --- TODO: Call Catalogue Microservice ---
        # This is the new "slow" part. It runs once per player.
        # catalogue_url = os.environ.get("CATALOGUE_SERVICE_URL")
        # try:
        #     response = requests.post(f"{catalogue_url}/cards/batch-lookup", json={"card_ids": deck_card_ids})
        #     response.raise_for_status()
        #     # We expect the catalogue to return the full stats map
        #     deck_stats_map = response.json() 
        # except requests.exceptions.RequestException as e:
        #     return jsonify({"msg": "Catalogue service unavailable"}), 503
        #
        # --- MOCK DATA (Remove when TODO is implemented) ---
        # This is the data structure we now store in the Match
        deck_stats_map = {}
        for card_id in deck_card_ids:
            deck_stats_map[card_id] = {
                "economy": random.randint(5, 15), 
                "food": random.randint(5, 15), 
                "environment": random.randint(5, 15), 
                "special": random.randint(0, 5), 
                "total": random.uniform(20.0, 40.0)
            }
        # --- END MOCK DATA ---

        # Assign the *full stats map* to the correct player
        if player_id == match.player1_id:
            match.player1_deck = deck_stats_map
        elif player_id == match.player2_id:
            match.player2_deck = deck_stats_map
        else:
            return jsonify({"msg": "Player is not part of this match"}), 403

        # If both decks are set, start the game
        if match.player1_deck is not None and match.player2_deck is not None:
            match.status = MatchStatus.IN_PROGRESS
            
        db.session.commit()
        return jsonify(match.to_dict(include_moves=False))
    
    except NotFound as e:
        return jsonify({"msg": str(e)}), 404
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error in choose_deck: {e}")
        return jsonify({"msg": "Internal server error"}), 500

@bp.post("/matches/<int:match_id>/moves")
def submit_move(match_id: int):
    """
    Submit a move (a card) for the current round.
    This is the core game logic endpoint.
    """
    payload = request.get_json(silent=True) or {}
    player_id = payload.get("player_id")
    card_id = payload.get("card_id") # This is the string ID of the card

    if not isinstance(player_id, int) or not isinstance(card_id, str):
        return jsonify({"msg": "player_id (int) and card_id (str) are required"}), 400

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

        # Get the player's deck stats map
        player_deck = match.player1_deck if player_id == match.player1_id else match.player2_deck
        if not player_deck:
            return jsonify({"msg": "Player deck not found or not set"}), 400
        
        # Validate the card is in the player's deck stats map 
        if card_id not in player_deck:
            return jsonify({"msg": f"Card {card_id} is not in the player's deck"}), 400
        
        # Get only the moves for the current round
        moves_this_round = db.session.scalars(
            db.select(Move).filter_by(
                match_id=match_id,
                round_number=match.current_round
            )
        ).all()

        if player_id in [m.player_id for m in moves_this_round]:
            return jsonify({"msg": "Player has already submitted a move for this round"}), 409
        
        # Check if card has already been played in previous rounds
        all_player_moves = db.session.scalars(
            db.select(Move).filter_by(
                match_id=match_id,
                player_id=player_id
            )
        ).all()
        
        if card_id in [m.card_id for m in all_player_moves]:
            return jsonify({"msg": f"Card {card_id} has already been played"}), 409

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
            db.session.commit()
            return jsonify({
                "status": "WAITING_FOR_OPPONENT",
                "move_submitted": move.to_dict()
            }), 200

        elif len(moves_this_round) == 1:
            # This is the second move. Process the round.
            move_p1 = moves_this_round[0]
            move_p2 = move # The new move we just created
            category = match.current_round_category

            # Retrieve stats *instantly* from the match object.
            try:
                # Get stats for each player's card (CORRECTED)
                if move_p1.player_id == match.player1_id:
                    p1_card_stats = match.player1_deck[move_p1.card_id]
                    p2_card_stats = match.player2_deck[move_p2.card_id]
                else:
                    p1_card_stats = match.player1_deck[move_p2.card_id]
                    p2_card_stats = match.player2_deck[move_p1.card_id]

                score_p1 = p1_card_stats[category]
                score_p2 = p2_card_stats[category]

            except KeyError as e:
                # This could happen if category or card_id is bad
                # This is now an internal logic error, not a network error
                current_app.logger.error(f"Error processing round: {e}")
                raise Exception(f"Card stats or category key error: {e}")

            round_winner_id = None
            if score_p1 > score_p2:
                round_winner_id = match.player1_id # Player 1 wins
            elif score_p2 > score_p1:
                round_winner_id = match.player2_id # Player 2 wins
            
            # Update score (handle P1/P2 correctly)
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
        db.session.rollback()
        current_app.logger.error(f"Error in submit_move: {e}")
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