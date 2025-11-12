# cards methods
from flask import Blueprint, jsonify
from .models.card import Card

catalogue = Blueprint("catalogue", __name__)

@catalogue.route("/cards", methods=["GET"])
def get_cards():
    # fetch all cards from the database
    cards = Card.query.all()

    # convert to json
    cards_json = [card.to_json() for card in cards]
    return jsonify({"data": cards_json})

@catalogue.route("/cards/<card_id>", methods=["GET"])
def get_single_card(card_id: int):
    try:
        int(card_id)
    except:
        return jsonify({"msg": "Invalid card ID"}), 400

    # fetch card by id
    card = Card.query.filter_by(id=card_id).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404

    # convert to json
    return jsonify(card.to_json())
