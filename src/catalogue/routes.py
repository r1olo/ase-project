"""Catalogue HTTP routes."""

from __future__ import annotations

from flask import Blueprint, jsonify

from .models import Card


bp = Blueprint("catalogue", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/cards")
def list_cards():
    cards = [card.to_dict() for card in Card.query.order_by(Card.id.asc()).all()]
    return jsonify({"data": cards})


@bp.get("/cards/<card_id>")
def get_card(card_id: str):
    if not card_id.isdigit():
        return jsonify({"msg": "Invalid card ID"}), 400

    card = Card.query.filter_by(id=int(card_id)).first()
    if not card:
        return jsonify({"msg": "Card not found"}), 404
    return jsonify(card.to_dict())
