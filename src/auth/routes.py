"""HTTP endpoints for the auth microservice."""

from __future__ import annotations

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


def _hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")


def _verify_password(password: str, pw_hash: str) -> bool:
    return bcrypt.check_password_hash(pw_hash, password)


def _store_refresh_token(user_id: int, jti: str, expires_in: int) -> None:
    redis_manager.conn.setex(f"refresh:{user_id}:{jti}", expires_in, "true")


def _revoke_all_refresh_tokens(user_id: int) -> None:
    pattern = f"refresh:{user_id}:*"
    for key in redis_manager.conn.scan_iter(match=pattern):
        redis_manager.conn.delete(key)


def _refresh_token_exists(user_id: int, jti: str) -> bool:
    return bool(redis_manager.conn.exists(f"refresh:{user_id}:{jti}"))


@bp.get("/health")
def health():
    return jsonify({"status": "ok"}), 200


@bp.post("/register")
def register():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")

    if not email or not password:
        return (
            jsonify({"msg": "Both email and password are required to register"}),
            400,
        )

    user = User(email=email, pw_hash=_hash_password(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"msg": "Email already registered"}), 409

    return jsonify({"msg": "Registered", "user_id": user.id}), 201


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password")

    if not email or not password:
        return jsonify({"msg": "Missing email or password"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not _verify_password(password, user.pw_hash):
        return jsonify({"msg": "Invalid credentials"}), 401

    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))
    decoded_refresh = decode_token(refresh_token)
    expires_in = int(decoded_refresh["exp"] - decoded_refresh["iat"])
    _store_refresh_token(user.id, decoded_refresh["jti"], expires_in)

    resp = jsonify({"access_token": access_token, "user_id": user.id})
    set_refresh_cookies(resp, refresh_token)
    return resp, 200


@bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = int(get_jwt_identity())
    jwt_payload = get_jwt()
    jti = jwt_payload["jti"]

    if not _refresh_token_exists(user_id, jti):
        return jsonify({"msg": "Invalid or expired refresh token"}), 401

    new_access_token = create_access_token(identity=str(user_id))
    return jsonify({"access_token": new_access_token})


@bp.post("/logout")
@jwt_required(refresh=True)
def logout():
    user_id = int(get_jwt_identity())
    _revoke_all_refresh_tokens(user_id)
    resp = jsonify({"msg": "Logged out"})
    unset_refresh_cookies(resp)
    return resp
