"""Players HTTP routes."""

from __future__ import annotations
import os
import jwt  # pip install pyjwt
import requests
from flask import Blueprint, jsonify, request, current_app
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_

from .extensions import db
from .models import PlayerProfile

bp = Blueprint("players", __name__)

# --- CONFIGURAZIONE ---
GAME_ENGINE_URL = os.environ.get("GAME_ENGINE_URL", "http://game-engine:5000")

# Carichiamo la chiave pubblica per verificare i token generati da Auth.
# In produzione, monta il file della chiave pubblica nel container.
AUTH_PUBLIC_KEY_PATH = os.environ.get("AUTH_PUBLIC_KEY_PATH", "jwtRS256.key.pub")
AUTH_PUBLIC_KEY = None

if os.path.exists(AUTH_PUBLIC_KEY_PATH):
    with open(AUTH_PUBLIC_KEY_PATH, "r") as f:
        AUTH_PUBLIC_KEY = f.read()
else:
    # Fallback per sviluppo locale se usi HS256 (Sconsigliato per microservizi reali)
    # Se Auth usa HS256, qui serve la stessa SECRET_KEY di Auth.
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "supersecretkey")


# --- HELPER PER IL JWT ---
def get_user_id_from_token():
    """
    Decodifica il JWT dall'header Authorization.
    Restituisce l'user_id (int) se valido, altrimenti None.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    try:
        # Formato header: "Bearer <token>"
        token = auth_header.split(" ")[1]
        
        if AUTH_PUBLIC_KEY:
            # Caso RS256 (Produzione): Verifichiamo con la Chiave Pubblica
            payload = jwt.decode(token, AUTH_PUBLIC_KEY, algorithms=["RS256"])
        else:
            # Caso HS256 (Sviluppo/Fallback): Verifichiamo con la Secret Key
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=["HS256"])
            
        # 'sub' è il campo standard dove flask_jwt_extended mette l'identity (user.id)
        return int(payload["sub"])
        
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, IndexError, ValueError) as e:
        current_app.logger.warning(f"Invalid JWT: {e}")
        return None


# --- ENDPOINTS ---

@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

# 1. GET /players/me (Check e Dati Profilo)
@bp.get("/players/me")
def get_my_profile():
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({"msg": "Missing or invalid authentication"}), 401

    profile = db.session.execute(
        db.select(PlayerProfile).filter_by(user_id=user_id)
    ).scalar_one_or_none()

    if not profile:
        # 404 dice al frontend: "Utente autenticato, ma non ha ancora creato il profilo Giocatore"
        return jsonify({"msg": "Profile not found", "action": "create_profile"}), 404
    
    return jsonify(profile.to_dict()), 200


# 2. POST /players (Creazione Profilo)
@bp.post("/players")
def create_profile():
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({"msg": "Missing or invalid authentication"}), 401

    # Check difensivo se esiste già
    existing = db.session.execute(
        db.select(PlayerProfile).filter_by(user_id=user_id)
    ).scalar_one_or_none()
    
    if existing:
        return jsonify({"msg": "Profile already exists"}), 409

    payload = request.get_json(silent=True) or {}
    
    username = (payload.get("username") or "").strip()
    if not username:
        return jsonify({"msg": "username is required"}), 400

    new_profile = PlayerProfile(
        user_id=user_id,
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


# 3. GET /players/<username> (Pubblico)
@bp.get("/players/<username>")
def get_player_public(username: str):
    profile = db.session.execute(
        db.select(PlayerProfile).filter_by(username=username)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Player not found"}), 404
    
    return jsonify(profile.to_dict()), 200


# --- PROXY VERSO GAME ENGINE ---

# 4. GET /history (Lista Partite)
@bp.get("/history")
def get_my_match_list():
    user_id = get_user_id_from_token()
    if not user_id:
        return jsonify({"msg": "Unauthorized"}), 401

    try:
        # Chiama il Game Engine filtrando per user_id
        resp = requests.get(
            f"{GAME_ENGINE_URL}/matches", 
            params={"user_id": user_id}, 
            timeout=5
        )
        
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching matches list"}), resp.status_code
            
        return jsonify(resp.json()), 200

    except requests.exceptions.RequestException:
        return jsonify({"msg": "Game Engine unavailable"}), 503


# 5. GET /history/<match_id> (Dettaglio Partita / Replay)
@bp.get("/history/<int:match_id>")
def get_match_details(match_id: int):
    if not get_user_id_from_token():
         return jsonify({"msg": "Unauthorized"}), 401

    try:
        target_url = f"{GAME_ENGINE_URL}/matches/{match_id}/history"
        resp = requests.get(target_url, timeout=5)
        
        if resp.status_code == 404:
            return jsonify({"msg": "Match not found"}), 404
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching match details"}), resp.status_code

        return jsonify(resp.json()), 200

    except requests.exceptions.RequestException:
        return jsonify({"msg": "Game Engine unavailable"}), 503


# 6. GET /leaderboard (Classifica Arricchita)
@bp.get("/leaderboard")
def get_leaderboard():
    try:
        resp = requests.get(f"{GAME_ENGINE_URL}/leaderboard", timeout=5)
        if resp.status_code != 200:
            return jsonify({"msg": "Error fetching leaderboard"}), resp.status_code
            
        leaderboard_data = resp.json() # Lista [{'user_id': 1, 'score': 10}, ...]

        if not leaderboard_data:
            return jsonify([]), 200

        # Estrazione user_ids
        user_ids = [entry['user_id'] for entry in leaderboard_data]

        # Query locale per ottenere gli username
        stmt = db.select(PlayerProfile).filter(PlayerProfile.user_id.in_(user_ids))
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