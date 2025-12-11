"""Card Catalogue HTTP routes."""
from __future__ import annotations
from .models import Card
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

bp = Blueprint("catalogue", __name__)

# check service status
@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

# get all cards details from db
@bp.get("/cards")
@jwt_required()
def get_all_cards():
    # fetch all cards from the database, ordering them by ascending order on id value
    cards = Card.query.order_by(Card.id.asc()).all()

    # convert to json
    cards_list = [card.to_dict(relative=True) for card in cards]
    return jsonify({"data": cards_list})

# get card details given its identifier
@bp.get("/cards/<card_id>")
@jwt_required()
def get_single_card(card_id: int):
    if not card_id.isdigit():
        return jsonify({"msg": "Invalid card ID"}), 400

    # fetch card by id
    card = Card.query.filter_by(id=int(card_id)).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404

    # convert to json
    return jsonify(card.to_dict(relative=True))

# check if deck is valid
@bp.post("/internal/cards/validation")
def validate_deck():
    payload = request.get_json(silent=True) or {}
    cards = []
    
    # checks each card in the payload
    for card_id in payload.get("data", []):
        # case no card ID or card ID is not a number
        if not card_id or not (isinstance(card_id, int) or card_id.isdigit()):
            return jsonify({"msg": "Empty deck"}), 400
        
        # case no match or match is wrong
        card = Card.query.filter_by(id=int(card_id)).first()
        if not card:
            return jsonify({"msg": "Invalid deck"}), 400
        cards.append(card.to_dict(relative=True))
    return jsonify({"data": cards})
