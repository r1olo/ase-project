"""Players HTTP routes."""

from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import PlayerProfile


bp = Blueprint("players", __name__)


def _parse_user_id(raw: str):
    if not raw.isdigit():
        return None
    return int(raw)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.get("/players/<user_id>")
def get_player(user_id: str):
    parsed = _parse_user_id(user_id)
    if parsed is None:
        return jsonify({"msg": "Invalid user id"}), 400

    profile = PlayerProfile.query.filter_by(user_id=parsed).first()
    if not profile:
        return jsonify({"msg": "Player not found"}), 404
    return jsonify(profile.to_dict())


@bp.post("/players/<user_id>")
def create_player(user_id: str):
    parsed = _parse_user_id(user_id)
    if parsed is None:
        return jsonify({"msg": "Invalid user id"}), 400

    if PlayerProfile.query.filter_by(user_id=parsed).first():
        return jsonify({"msg": "Profile already exists"}), 409

    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    display_name = (payload.get("display_name") or "").strip() or username
    profile_picture = payload.get("profile_picture")
    bio = payload.get("bio")

    if not username:
        return jsonify({"msg": "username is required"}), 400

    profile = PlayerProfile(
        user_id=parsed,
        username=username,
        display_name=display_name,
        profile_picture=profile_picture,
        bio=bio,
    )
    db.session.add(profile)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "username already taken"}), 409

    return jsonify(profile.to_dict()), 201


@bp.put("/players/<user_id>")
def update_player(user_id: str):
    parsed = _parse_user_id(user_id)
    if parsed is None:
        return jsonify({"msg": "Invalid user id"}), 400

    profile = PlayerProfile.query.filter_by(user_id=parsed).first()
    if not profile:
        return jsonify({"msg": "Player not found"}), 404

    payload = request.get_json(silent=True) or {}
    if "username" in payload:
        username = payload["username"].strip()
        if not username:
            return jsonify({"msg": "username cannot be empty"}), 400
        profile.username = username
    if "display_name" in payload:
        display_name = payload["display_name"].strip()
        if display_name:
            profile.display_name = display_name
    if "profile_picture" in payload:
        profile.profile_picture = payload["profile_picture"]
    if "bio" in payload:
        profile.bio = payload["bio"]

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "username already taken"}), 409

    return jsonify(profile.to_dict())
