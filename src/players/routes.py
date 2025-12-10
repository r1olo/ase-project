"""Players HTTP routes."""
from __future__ import annotations
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from common.extensions import db
from .models import Player

bp = Blueprint("players", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


# 1. GET /players/me
@bp.get("/players/me")
@jwt_required()
def get_my_profile():
    current_user_id = int(get_jwt_identity()) 

    profile = db.session.execute(
        db.select(Player).filter_by(user_id=current_user_id)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Profile not found", "action": "create_profile"}), 404
    
    return jsonify(profile.to_dict()), 200


# 2. POST /players
@bp.post("/players")
@jwt_required()
def create_profile():
    current_user_id = int(get_jwt_identity())
    
    existing = db.session.execute(
        db.select(Player).filter_by(user_id=current_user_id)
    ).scalar_one_or_none()
    
    if existing:
        return jsonify({"msg": "Profile already exists"}), 409

    payload = request.get_json(silent=True) or {}
    
    username = (payload.get("username") or "").strip()
    if not username:
        return jsonify({"msg": "username is required"}), 400

    region_value = (payload.get("region") or "").strip() or None

    new_profile = Player(
        user_id=current_user_id, 
        username=username,
        region=region_value
    )

    db.session.add(new_profile)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "Username already taken"}), 409

    return jsonify(new_profile.to_dict()), 201

# 3. GET /players/<username>
@bp.get("/players/<username>")
@jwt_required()
def get_player_public(username: str):
    profile = db.session.execute(
        db.select(Player).filter_by(username=username)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Player not found"}), 404
    
    return jsonify(profile.to_dict()), 200

# 4. PATCH /players/me (Modifica profilo)
@bp.patch("/players/me")
@jwt_required()
def update_profile():
    current_user_id = int(get_jwt_identity())

    # Recuperiamo il profilo esistente
    profile = db.session.execute(
        db.select(Player).filter_by(user_id=current_user_id)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Profile not found"}), 404

    # Leggiamo i dati inviati
    payload = request.get_json(silent=True) or {}

    # Aggiorniamo la REGION solo se è presente nel payload
    if "region" in payload:
        profile.region = (payload.get("region") or "").strip() or None

    # Non tocchiamo 'username' o 'user_id'. 
    # Se l'utente prova a inviarli, vengono semplicemente ignorati.

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Error updating profile"}), 500

    return jsonify(profile.to_dict()), 200

# 5. GET /internal/players/validation
@bp.get("/internal/players/validation")
def validate_player():
    # Recuperiamo lo user_id dai parametri GET (es. ?user_id=123)
    target_user_id = request.args.get("user_id", type=int)

    if not target_user_id:
        return jsonify({"msg": "user_id is required"}), 400

    # Verifichiamo se esiste una riga nel DB con questo user_id.
    # Usiamo db.select(Player.id) per efficienza: ci basta sapere se esiste.
    exists = db.session.execute(
        db.select(Player.id).filter_by(user_id=target_user_id)
    ).first() is not None

    # Se esiste, significa che ha completato la registrazione (ha username).
    return jsonify({"valid": exists}), 200