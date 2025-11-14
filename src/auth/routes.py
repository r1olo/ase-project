# HTTP endpoints for Auth
from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    set_refresh_cookies,
    unset_refresh_cookies,
)
from sqlalchemy.exc import IntegrityError

from common.extensions import bcrypt, db, redis_manager
from .models import User

bp = Blueprint("auth", __name__)

# hash a password
def _hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")

# verify a password against a hash
def _verify_password(password: str, pw_hash: str) -> bool:
    return bcrypt.check_password_hash(pw_hash, password)

# store refresh token in redis
def _store_refresh_token(user_id: int, jti: str, expires_in: int) -> None:
    redis_manager.conn.setex(f"refresh:{user_id}:{jti}", expires_in, "true")

# revoke all refresh tokens
def _revoke_all_refresh_tokens(user_id: int) -> None:
    pattern = f"refresh:{user_id}:*"
    for key in redis_manager.conn.scan_iter(match=pattern):
        redis_manager.conn.delete(key)

# check whether redis has a refresh token
def _refresh_token_exists(user_id: int, jti: str) -> bool:
    return bool(redis_manager.conn.exists(f"refresh:{user_id}:{jti}"))

# register a user
@bp.post("/register")
def register():
    # extract stuff
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")

    # check that both are supplied
    if not email or not password:
        return (jsonify({"msg": "Both email and password are required to register"}),
            400)

    # create a user or fail gracefully
    user = User(email=email, pw_hash=_hash_password(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "User already registered"}), 409

    # success
    return jsonify({"msg": "Registered", "user_id": user.id}), 201

# login and generate tokens
@bp.post("/login")
def login():
    # extract stuff
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")

    # check if everything is supplied
    if not email or not password:
        return jsonify({"msg": "Missing email or password"}), 400

    # check if user exists and his password
    user = User.query.filter_by(email=email).first()
    if not user or not _verify_password(password, user.pw_hash):
        return jsonify({"msg": "Invalid credentials"}), 401

    # generate token and store it in redis
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    decoded_refresh = decode_token(refresh_token)
    expires_in = int(decoded_refresh["exp"] - decoded_refresh["iat"])
    _store_refresh_token(user.id, decoded_refresh["jti"], expires_in)

    # return everything to user
    resp = jsonify({"access_token": access_token, "user_id": user.id})
    set_refresh_cookies(resp, refresh_token)
    return resp, 200

# refresh an access token and return it
@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    # extract stuff
    user_id = int(get_jwt_identity())
    jwt_payload = get_jwt()
    jti = jwt_payload["jti"]

    # check if redis has the refresh token
    if not _refresh_token_exists(user_id, jti):
        return jsonify({"msg": "Invalid or expired refresh token"}), 401

    # generate a new access token
    new_access_token = create_access_token(identity=str(user_id))
    return jsonify({"access_token": new_access_token})

# logout and clear every refresh token
@bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    # revoke all tokens and unset cookies
    user_id = int(get_jwt_identity())
    _revoke_all_refresh_tokens(user_id)
    resp = jsonify({"msg": "Logged out"})
    unset_refresh_cookies(resp)
    return resp
