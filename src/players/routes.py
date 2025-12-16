"""Players HTTP routes."""
from __future__ import annotations
from enum import StrEnum
from flask import Blueprint, jsonify, request
import re
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from common.extensions import db
from .models import Player, Friendship, Region

bp = Blueprint("players", __name__)
 
class UsernameError(StrEnum):
    USERNAME_REQUIRED = "Username is required"
    LENGTH_TOO_SHORT = "Username too short"
    LENGTH_TOO_LONG = "Username too long"
    INVALID_USERNAME = "Invalid username"

# Utility function to validate username
def _validate_username(input: str) -> UsernameError | None:
    if not input:
        return UsernameError.USERNAME_REQUIRED
    if len(input) < 3:
        return UsernameError.LENGTH_TOO_SHORT
    if len(input) > 80:
        return UsernameError.LENGTH_TOO_LONG
    if not re.fullmatch(r'[a-zA-Z0-9_-]+', input):
        return UsernameError.INVALID_USERNAME
    return None

# Utility function to validate region
def _validate_region(region_input: str | None) -> str | None:
    """
    Returns the valid region if present in the Enum, None if empty.
    Raises ValueError if the string is invalid.
    """
    cleaned = (region_input or "").strip()
    if not cleaned:
        return None
    
    # Check if the value exists in the Enum (e.g. "Sicilia")
    # If cleaned is not in the enum, this line will raise ValueError
    return Region(cleaned).value

@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200

# Player table
# 1. POST /players
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
    
    username = (payload.get("username") or "")
    # Input sanitization
    result = _validate_username(username)
    if result:
        return jsonify({"msg": result.value}), 400

    # Region validation
    try:
        region_value = _validate_region(payload.get("region"))
    except ValueError:
        # If user typed "sicilia" instead of "Sicilia"
        valid_regions = [r.value for r in Region]
        return jsonify({
            "msg": "Invalid region", 
            "valid_options": valid_regions
        }), 400
    
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

# 2. GET /players/me
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

# 3. PATCH /players/me (Update profile)
@bp.patch("/players/me")
@jwt_required()
def update_profile():
    current_user_id = int(get_jwt_identity())

    # Retrieve existing profile
    profile = db.session.execute(
        db.select(Player).filter_by(user_id=current_user_id)
    ).scalar_one_or_none()

    if not profile:
        return jsonify({"msg": "Profile not found"}), 404

    # Read sent data
    payload = request.get_json(silent=True) or {}

    # Update REGION only if present in payload
    if "region" in payload:
        try:
            # Validate using the same logic (Enum)
            profile.region = _validate_region(payload.get("region"))
        except ValueError:
            valid_regions = [r.value for r in Region]
            return jsonify({
                "msg": "Invalid region",
                "valid_options": valid_regions
            }), 400

    # Do not touch 'username' or 'user_id'. 
    # If user tries to send them, they are simply ignored.
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return jsonify({"msg": "Error updating profile"}), 500

    return jsonify(profile.to_dict()), 200

# 4. GET /players/<player_id> (Find profile by ID)
@bp.get("/players/<int:player_id>")
@jwt_required()
def get_player_by_id(player_id: int):
    # Flask automatically extracts "player_id" from URL and passes it here.

    # Search in DB
    profile = db.session.execute(
        db.select(Player).filter_by(user_id=player_id)
    ).scalar_one_or_none()

    if profile is None:
        return jsonify({"msg": "Player not found"}), 404
    
    return jsonify(profile.to_dict()), 200

# 5. GET /players/search/<username> (Search profile by username)
@bp.get("/players/search/<string:username>")
@jwt_required()
def get_player_by_username(username):
    # Flask automatically extracts "username" from URL and passes it here.

    # Input sanitization
    result = _validate_username(username)
    if result:
        return jsonify({"msg": result.value}), 400

    # Search in DB using username field
    profile = db.session.execute(
        db.select(Player).filter_by(username=username)
    ).scalar_one_or_none()

    if profile is None:
        return jsonify({"msg": "Player not found"}), 404
    
    return jsonify(profile.to_dict()), 200

# 6. POST /internal/players/validation
@bp.post("/internal/players/validation")
def validate_player():
    payload = request.get_json(silent=True) or {}
    
    # Extract raw value
    target_user_id = payload.get("user_id")

    # RIGOROUS type check:
    # Accepts only real integers (e.g. 123 or 0).
    # Rejects strings (e.g. "123"), booleani, floats or None.
    if type(target_user_id) is not int:
        return jsonify({"msg": "user_id must be a valid integer (no strings allowed)"}), 400

    # If here, target_user_id is definitely an integer (e.g. 123 or 0)
    
    # Verify in DB
    exists = db.session.execute(
        db.select(Player.id).filter_by(user_id=target_user_id)
    ).first() is not None

    return jsonify({"valid": exists}), 200

# Friendship table
def _get_friendship_by_ids(player1_id: int, player2_id: int) -> Friendship | None:
    if not isinstance(player1_id, int) or not isinstance(player2_id, int):
        return None

    # Swap values if necessary
    if player1_id > player2_id:
        player1_id, player2_id = player2_id, player1_id
    return Friendship.query.filter_by(player1_id=player1_id, player2_id=player2_id).first()

# 7. GET /players/me/friends (Get friends list)
@bp.get("/players/me/friends")
@jwt_required()
def get_my_friends():
    current_user_id = int(get_jwt_identity())
    current_player = Player.query.filter_by(user_id=current_user_id).first()
    if not current_player:
        return jsonify({"msg": "User player not found"}), 404

    # Get the list of friends of the current user
    friends = Player.query.with_entities(Player.username, Friendship.accepted).join(
        Friendship,
        or_(
            (Friendship.player1_id == current_player.id) & (Friendship.player2_id == Player.id),
            (Friendship.player2_id == current_player.id) & (Friendship.player1_id == Player.id)
        )
    ).all()

    if not friends:
        return jsonify({"data": []}), 200
    friends_list = [
        {"username": username, "status": "accepted" if accepted else "pending"}
        for username, accepted in friends
    ]
    return jsonify({"data": friends_list}), 200

# 8. GET /players/me/friends/<username> (Check friendship status)
@bp.get("/players/me/friends/<string:username>")
@jwt_required()
def get_friendship_status(username: str):
    # Input sanitization
    result = _validate_username(username)
    if result:
        return jsonify({"msg": result.value}), 400
    
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

# 9. POST /players/me/friends/<username> (Handle friend request)
# Notice: status of new created friendship is pending by default
@bp.post("/players/me/friends/<string:username>")
@jwt_required()
def handle_friend_request(username: str):
    # Input sanitization
    result = _validate_username(username)
    if result:
        return jsonify({"msg": result.value}), 400
    
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
    # Case: friendship does not exist
    if not friendship:
        # Create new request
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

    # Case: friendship exists
    if friendship.accepted:
        return jsonify({"msg": "You are already friends"}), 409

    # Case: pending friendship request - check requester
    if friendship.requester_id == current_player.id:
        return jsonify({"msg": "Friend request is pending"}), 409

    # Case: incoming request - process response
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

# 10. DELETE /players/me/friends/<username> (Remove friend)
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
    
    # If friendship request is still pending, so that the status accepted is set to false, only the requester user can remove it
    if not friendship.accepted and not friendship.requester_id == current_player.id:
        return jsonify({"msg": "Only requester can remove friendship"}), 409

    db.session.delete(friendship)
    db.session.commit()
    return jsonify({"msg": "Friendship removed"}), 200

# 11. POST /internal/players/friendship/validation (Validate friendship)
@bp.post("/internal/players/friendship/validation")
def validate_friendship():
    payload = request.get_json(silent=True) or {}
    user1_id, user2_id = payload.get("player1_id"), payload.get("player2_id")

    # Check if both keys are specified
    if user1_id is None or user2_id is None:
        return jsonify({"msg": "Both player IDs are required"}), 400
    
    # Check if values are in the expected format
    if not isinstance(user1_id, int) or not isinstance(user2_id, int):
        return jsonify({"msg": "Invalid player IDs"}), 400
    
    # Check if both players exist
    player1 = Player.query.filter_by(user_id=user1_id).first()
    if not player1:
        return jsonify({"msg": "First player not found"}), 404
    player2 = Player.query.filter_by(user_id=user2_id).first()
    if not player2:
        return jsonify({"msg": "Second player not found"}), 404

    result = _get_friendship_by_ids(player1.id, player2.id)
    return jsonify({"valid": result is not None}), 200
