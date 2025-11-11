# cards methods
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from .extensions import db
from .models.card import Card

catalogue = Blueprint("catalogue", __name__)

@catalogue.route("/cards", methods=["GET"])
def get_cards():
    # fetch all cards from the database
    cards = Card.query.all()

    # convert to json
    cards_json = [card.to_json() for card in cards]
    return jsonify({"data": cards_json})

@catalogue.route("/cards/<int:card_id>", methods=["GET"])
def get_single_card(card_id: int):
    # fetch card by id
    card = Card.query.filter_by(id=card_id).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404

    # convert to json
    return jsonify(card.to_json())
