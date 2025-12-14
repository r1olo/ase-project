"""Players HTTP routes."""
from __future__ import annotations
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from common.extensions import db
from .models import Player, Friendship


bp = Blueprint("players", __name__)


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


# player table
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

# 3. POST /players/search (Cerca profilo pubblico)
@bp.post("/players/search")
@jwt_required()
def search_player():
    # Leggiamo il JSON dal body
    payload = request.get_json(silent=True) or {}
    
    # Estraiamo lo username da cercare
    target_username = (payload.get("username") or "").strip()

    if not target_username:
        return jsonify({"msg": "Username is required"}), 400

    # Cerchiamo nel DB
    profile = db.session.execute(
        db.select(Player).filter_by(username=target_username)
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

# 5. POST /internal/players/validation
@bp.post("/internal/players/validation")
def validate_player():
    # Leggiamo il payload JSON dal body della richiesta
    payload = request.get_json(silent=True) or {}

    # Estraiamo lo user_id
    target_user_id = payload.get("user_id")

    # Validazione: user_id deve essere presente
    if not target_user_id:
        return jsonify({"msg": "user_id is required"}), 400

    # Verifichiamo l'esistenza nel DB
    exists = db.session.execute(
        db.select(Player.id).filter_by(user_id=target_user_id)
    ).first() is not None

    return jsonify({"valid": exists}), 200


# friendship table
def _get_friendship_by_ids(player1_id: int, player2_id: int) -> Friendship | None:
    # swap values if necessary
    if player1_id > player2_id:
        player1_id, player2_id = player2_id, player1_id
    return Friendship.query.filter_by(player1_id=player1_id, player2_id=player2_id).first()

# get friends list of current user
@bp.get("/players/me/friends")
@jwt_required()
def get_my_friends():
    current_user_id = int(get_jwt_identity())
    current_player = Player.query.filter_by(user_id=current_user_id).first()
    if not current_player:
        return jsonify({"msg": "User player not found"}), 404

    # get the list of friends of the current user
    friends = Player.query.with_entities(Player.username, Friendship.accepted).join(
        Friendship,
        or_(
            (Friendship.player1_id == current_player.id) & (Friendship.player2_id == Player.id),
            (Friendship.player2_id == current_player.id) & (Friendship.player1_id == Player.id)
        )
    ).all()

    friends_list = [
        {"username": username, "status": "accepted" if accepted else "pending"}
        for username, accepted in friends
    ]
    return jsonify({"data": friends_list}), 200

# check friendship status between current user and user with param username
@bp.get("/players/me/friends/<username>")
@jwt_required()
def get_friendship_status(username: str):
    current_user_id = int(get_jwt_identity())
    current_player = Player.query.filter_by(user_id=current_user_id).first()
    if not current_player:
        return jsonify({"msg": "User player not found"}), 404

    target_player = Player.query.filter_by(username=username).first()
    if not target_player:
        return jsonify({"msg": "Target player not found"}), 404

    friendship = _get_friendship_by_ids(current_player.id, target_player.id)
    if not friendship:
        return jsonify({"msg": "Friendship not found"}), 404

    status = "accepted" if friendship.accepted else "pending"
    return jsonify({"username": username, "status": status}), 200

# send or respond to a friendship request
# notice: status of new created friendship is pending by default
@bp.post("/players/me/friends/<username>")
@jwt_required()
def handle_friend_request(username):
    current_user_id = int(get_jwt_identity())
    current_player = Player.query.filter_by(user_id=current_user_id).first()
    if not current_player:
        return jsonify({"msg": "User player not found"}), 404

    target_player = Player.query.filter_by(username=username).first()
    if not target_player:
        return jsonify({"msg": "Player not found"}), 404

    if current_player.id == target_player.id:
        return jsonify({"msg": "You cannot add yourself as a friend"}), 400

    friendship = _get_friendship_by_ids(current_player.id, target_player.id)
    # case: friendship does not exist
    if not friendship:
        # create new request
        if current_player.id < target_player.id:
            p1, p2 = current_player.id, target_player.id
        else:
            p1, p2 = target_player.id, current_player.id
            
        new_friendship = Friendship(
            player1_id=p1,
            player2_id=p2,
            requester_id=current_player.id,
            accepted=False
        )
        db.session.add(new_friendship)
        db.session.commit()
        return jsonify({"msg": "Friend request sent"}), 201

    # case: friendship exists
    if friendship.accepted:
        return jsonify({"msg": "You are already friends"}), 409

    # case: pending friendship request - check requester
    if friendship.requester_id == current_player.id:
        return jsonify({"msg": "Friend request is pending"}), 409

    # case: incoming request - process response
    payload = request.get_json(silent=True) or {}
    accepted = payload.get("accepted")
    if accepted is None:
        return jsonify({"msg": "Provide 'accepted' to respond."}), 400
    if accepted:
        friendship.accepted = True
        msg = "Friend request accepted"
    else:
        db.session.delete(friendship)
        msg = "Friend request rejected"

    db.session.commit()
    return jsonify({"msg": msg}), 200

# remove friendship between current user and user with param username
@bp.delete("/players/me/friends/<username>")
@jwt_required()
def remove_friend(username):
    current_user_id = int(get_jwt_identity())
    current_player = Player.query.filter_by(user_id=current_user_id).first()
    if not current_player:
        return jsonify({"msg": "User player not found"}), 404

    target_player = Player.query.filter_by(username=username).first()
    if not target_player:
        return jsonify({"msg": "Target player not found"}), 404

    friendship = _get_friendship_by_ids(current_player.id, target_player.id)
    if not friendship:
        return jsonify({"msg": "Friendship not found"}), 404
    
    # if friendship request is still pending, so that the status accepted is set to false, only the requester user can remove it
    if not friendship.accepted and not friendship.requester_id == current_player.id:
        return jsonify({"msg": "Only requester can remove friendship"}), 409

    db.session.delete(friendship)
    db.session.commit()
    return jsonify({"msg": "Friendship removed"}), 200

# check if two players are friends
bp.get("/internal/players/friendship/validation")
def validate_friendship(player1_id: int, player2_id: int):
    return _get_friendship_by_ids(player1_id, player2_id)