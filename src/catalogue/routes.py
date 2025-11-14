"""Card Catalogue HTTP routes."""
from __future__ import annotations
from .models import Card
from flask import Blueprint, jsonify, request

catalogue = Blueprint("catalogue", __name__)

@catalogue.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

@catalogue.route("/cards", methods=["GET"])
def get_cards():
    # fetch all cards from the database, ordering them by ascending order on id value
    cards = Card.query.order_by(Card.id.asc()).all()

    # convert to json
    cards_json = [card.to_json() for card in cards]
    return jsonify({"data": cards_json})

@catalogue.route("/cards/<card_id>", methods=["GET"])
def get_single_card(card_id: int):
    if not card_id.isdigit():
        return jsonify({"msg": "Invalid card ID"}), 400

    # fetch card by id
    card = Card.query.filter_by(id=int(card_id)).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404

    # convert to json
    return jsonify(card.to_json())

@catalogue.route("/cards/validation", methods=["GET"])
def validate_deck():
    payload = request.get_json(silent=True) or {}
    # checks each card in the payload
    for card in payload.get("data", []):
        if not card:
            return jsonify({"data": False})
        
        # case no match or match is wrong
        card_catalogue = Card.query.filter_by(id=card.get("id") or "").first()
        if not card_catalogue or not card_catalogue.to_json() == card:
            return jsonify({"data": False})
    return jsonify({"data": True})
