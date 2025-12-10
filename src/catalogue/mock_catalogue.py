"""Card Catalogue HTTP routes."""
from __future__ import annotations
from flask import Blueprint, current_app, jsonify, request

import json

mock_catalogue = Blueprint("mock_catalogue", __name__)

# fill the database at init
def _init_mock_cards_db():
    current_app.cards_db = {}
    with open("cards/cards.json") as file:
        cards = json.load(file)
        for idx, card in enumerate(cards):
            card["id"] = idx + 1
        current_app.cards_db = cards

def query_db_by_id(id: int):
    for card in current_app.cards_db.values():
        if card["id"] == id:
            return card
    return None

@mock_catalogue.route("/cards", methods=["GET"])
def get_cards():
    current_app.cards_db
    cards = [card for _, card in current_app.cards_db.items()]
    return jsonify({"data": cards})

@mock_catalogue.route("/cards/<card_id>", methods=["GET"])
def get_single_card(card_id: int):
    if not card_id.isdigit():
        return jsonify({"msg": "Invalid card ID"}), 400

    card = query_db_by_id(int(card_id))
    return jsonify(card) if card else jsonify({"msg": "Card not found"}), 404


@mock_catalogue.route("/internal/cards/validation", methods=["POST"])
def validate_deck():
    payload = request.get_json(silent=True) or {}
    cards = []

    for card_id in payload.get("data", []):
        if not card_id or not (isinstance(card_id, int) or card_id.isdigit()):
            return jsonify({"msg": "Empty deck"}), 400
        
        card = query_db_by_id(int(card_id))
        if not card:
            return jsonify({"msg": "Invalid deck"}), 400
        cards.append(card.to_dict(relative=True))
    return jsonify({"data": cards})
