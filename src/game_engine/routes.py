"""Game engine HTTP routes."""

from __future__ import annotations

import json
import uuid

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import NotFound

from .extensions import db
from .models import Match, Round


bp = Blueprint("game_engine", __name__)


def _match_or_404(public_id: str) -> Match:
    match = Match.query.filter_by(public_id=public_id).first()
    if not match:
        raise NotFound(description="Match not found")
    return match


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.post("/matches")
def create_match():
    payload = request.get_json(silent=True) or {}
    participants = payload.get("participants") or []
    if not isinstance(participants, list) or len(participants) < 2:
        return jsonify({"msg": "participants must be a list with at least 2 entries"}), 400

    public_id = uuid.uuid4().hex[:12]
    match = Match(
        public_id=public_id,
        status="pending",
        metadata=json.dumps({"participants": participants}),
    )
    db.session.add(match)
    db.session.commit()
    return jsonify(match.to_dict()), 201


@bp.get("/matches/<public_id>")
def get_match(public_id: str):
    match = _match_or_404(public_id)
    return jsonify(match.to_dict())


@bp.post("/matches/<public_id>/rounds")
def record_round(public_id: str):
    match = _match_or_404(public_id)

    payload = request.get_json(silent=True) or {}
    round_number = payload.get("round_number")
    state = payload.get("state")
    outcome = payload.get("outcome")

    if not isinstance(round_number, int) or round_number < 1:
        return jsonify({"msg": "round_number must be a positive integer"}), 400

    round_record = Round(
        match=match,
        round_number=round_number,
        state=json.dumps(state) if state is not None else None,
        outcome=outcome,
    )
    db.session.add(round_record)
    match.status = payload.get("status") or match.status
    db.session.commit()
    return jsonify(round_record.to_dict()), 201
