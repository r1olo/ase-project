"""Card Catalogue HTTP routes."""
from __future__ import annotations
from .models import Card
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

catalogue = Blueprint("catalogue", __name__)

@catalogue.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@catalogue.route("/cards", methods=["GET"])
@jwt_required()
def get_cards():
    # fetch all cards from the database, ordering them by ascending order on id value
    cards = Card.query.order_by(Card.id.asc()).all()

    # convert to json
    cards_json = [card.to_json(relative=True) for card in cards]
    return jsonify({"data": cards_json})

@catalogue.route("/cards/<card_id>", methods=["GET"])
@jwt_required()
def get_single_card(card_id: int):
    if not card_id.isdigit():
        return jsonify({"msg": "Invalid card ID"}), 400

    # fetch card by id
    card = Card.query.filter_by(id=int(card_id)).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404

    # convert to json
    return jsonify(card.to_json(relative=True))

@catalogue.route("/internal/cards/validation", methods=["POST"])
def validate_deck():
    payload = request.get_json(silent=True) or {}
    cards = []
    
    # checks each card in the payload
    for card_id in payload.get("data", []):
        # case no card ID or card ID is not a number
        if not card_id or not isinstance(card_id, int) or not card_id.isdigit():
            return jsonify({"msg": "Empty deck"}), 400
        
        # case no match or match is wrong
        card = Card.query.filter_by(id=int(card_id)).first()
        if not card:
            return jsonify({"msg": "Invalid deck"}), 400
        cards.append(card.to_json(relative=True))
    return jsonify({"data": cards})

# @catalogue.route("/cards/validation", methods=["GET"])
# def validate_deck():
#     payload = request.get_json(silent=True) or {}

#     # checks each card in the payload
#     for card in payload.get("data", []):
#         if not card:
#             return jsonify({"data": False})
        
#         # case no match or match is wrong
#         card_catalogue = Card.query.filter_by(id=card.get("id") or "").first()
#         if not card_catalogue or not card_catalogue.to_json(relative=True) == card:
#             return jsonify({"data": False})
#     return jsonify({"data": True})
