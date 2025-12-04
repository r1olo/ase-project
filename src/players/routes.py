"""Players HTTP routes."""
from __future__ import annotations
import os
import requests
from flask import Blueprint, jsonify, request, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from common.extensions import db
from .models import Player

bp = Blueprint("players", __name__)

def _game_engine_url():
    return current_app.config.get("GAME_ENGINE_URL", "https://game-engine:5000")

@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

# 1. GET /players/me
@bp.get("/players/me")
@jwt_required()
def get_my_profile():
    # get_jwt_identity() restituisce l'user_id (dal campo 'sub' del token)
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

    new_profile = Player(
        user_id=current_user_id, 
        username=username,
        profile_picture=payload.get("profile_picture"),
        region=payload.get("region")
    )

    db.session.add(new_profile)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "Username already taken"}), 409

    return jsonify(new_profile.to_dict()), 201


# 3. GET /players/<username> (Pubblico - Nessun JWT richiesto)
@bp.get("/players/<username>")
def get_player_public(username: str):
    profile = db.session.execute(
        db.select(Player).filter_by(username=username)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Player not found"}), 404
    
    return jsonify(profile.to_dict()), 200


# --- PROXY VERSO GAME ENGINE ---

# 4. GET /history (Lista Partite)
@bp.get("/history")
@jwt_required() 
def get_my_match_list():
    current_user_id = get_jwt_identity() # Prende l'ID dal token validato
    
    try:
        # Chiama il Game Engine filtrando per user_id
        resp = requests.get(
            f"{_game_engine_url()}/matches", 
            params={"user_id": current_user_id}, 
            timeout=5
        )
        
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching matches list"}), resp.status_code
            
        return jsonify(resp.json()), 200

    except requests.exceptions.RequestException:
        return jsonify({"msg": "Game Engine unavailable"}), 503


# 5. GET /history/<match_id> (Dettaglio Partita / Replay)
@bp.get("/history/<int:match_id>")
@jwt_required() 
def get_match_details(match_id: int):
    # Qui verifichiamo solo che l'utente sia loggato.
    
    try:
        target_url = f"{_game_engine_url}/matches/{match_id}/history"
        resp = requests.get(target_url, timeout=5)
        
        if resp.status_code == 404:
            return jsonify({"msg": "Match not found"}), 404
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching match details"}), resp.status_code

        return jsonify(resp.json()), 200

    except requests.exceptions.RequestException:
        return jsonify({"msg": "Game Engine unavailable"}), 503


# 6. GET /leaderboard (Classifica Arricchita - Pubblica)
@bp.get("/leaderboard")
def get_leaderboard():
    try:
        resp = requests.get(f"{_game_engine_url}/leaderboard", timeout=5)
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching leaderboard"}), resp.status_code
            
        leaderboard_data = resp.json() # Lista [{'user_id': 1, 'score': 10}, ...]

        if not leaderboard_data:
            return jsonify([]), 200

        # Estrazione user_ids
        user_ids = [entry['user_id'] for entry in leaderboard_data]

        # Query locale per ottenere gli username
        stmt = db.select(Player).filter(Player.user_id.in_(user_ids))
        profiles = db.session.execute(stmt).scalars().all()

        # Mappa ID -> Username
        id_to_username = {p.user_id: p.username for p in profiles}

        # Arricchimento
        final_data = []
        for entry in leaderboard_data:
            uid = entry.get('user_id')
            entry['username'] = id_to_username.get(uid, "Unknown Player")
            final_data.append(entry)

        return jsonify(final_data), 200

    except requests.exceptions.RequestException:
        return jsonify({"msg": "Game Engine unavailable"}), 503