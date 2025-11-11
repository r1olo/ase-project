# authentication methods
from flask import Blueprint, request, jsonify, make_response
from flask_jwt_extended import (
        decode_token,
        create_access_token,
        create_refresh_token,
        jwt_required,
        get_jwt_identity,
        get_jwt
)
from .extensions import bcrypt, db, redis
from .models.user import User

auth = Blueprint("auth", __name__)

### helper functions

# use bcrypt to generate a password hash
def hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")

# test a password against a hash
def test_password(password: str, hash: str) -> bool:
    return bcrypt.check_password_hash(hash, password)

# store the fresh token in redis with an expiration
# key pattern: refresh:{user_id}:{uuid}
def store_refresh_token(user_id: int, jti: str, expires_in: int):
    redis.conn.setex(f"refresh:{user_id}:{jti}", expires_in, "true")

# verify if the given refresh token exists in redis for that user
def is_refresh_token_valid(user_id: int, jti: str) -> bool:
    return redis.conn.exists(f"refresh:{user_id}:{jti}")

# remove a specific refresh token
def revoke_refresh_token(user_id: int, jti: str):
    redis.conn.delete(f"refresh:{user_id}:{jti}")

# remove all refresh tokens for a user
def revoke_all_refresh_tokens(user_id: int):
    for key in redis.conn.scan_iter(match=f"refresh:{user_id}:*"):
        redis.conn.delete(key)

# you can login with username/password or email/password (both is handled fine,
# username takes priority)
@auth.route("/login", methods=["POST"])
def login():
    # extract stuff
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    # missing username/email or password
    if not (username or email) or not password:
        return jsonify({"msg": "Missing username/email or password"}), 400

    # try to extract user
    if username:
        user = User.query.filter_by(user=username).first()
    else:
        user = User.query.filter_by(email=email).first()

    # check user and supplied password against stored hash
    if not user or not test_password(password, user.pw_hash):
        return jsonify({"msg": "Invalid credentials"}), 401

    # create tokens
    access_token = create_access_token(identity=str(user.id))
    refresh_token = create_refresh_token(identity=str(user.id))

    # extract jti and expiry of this refresh token
    decoded_refresh = decode_token(refresh_token)
    jti = decoded_refresh["jti"]
    exp_timestamp = decoded_refresh["exp"]
    expires_in = int(exp_timestamp - decoded_refresh["iat"])

    # store refresh jti in redis
    store_refresh_token(user.id, jti, expires_in)

    # send refresh token as HttpOnly cookie
    resp = make_response(jsonify(access_token=access_token))
    resp.set_cookie("refresh_token", refresh_token, httponly=True,
                    secure=True, samesite="Strict", max_age=expires_in,
                    path="/refresh")
    return resp

@auth.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    # use the refresh token from cookie to issue a new access token
    user_id = int(get_jwt_identity())
    jwt_data = get_jwt()
    jti = jwt_data["jti"]

    # check redis for validity
    if not is_refresh_token_valid(user_id, jti):
        return jsonify({"msg": "Invalid or expired refresh token"}), 401

    # issue new access token
    access_token = create_access_token(identity=user_id)
    return jsonify(access_token=access_token)

@auth.route("/logout", methods=["POST"])
@jwt_required(refresh=True)
def logout():
    # revoke the refresh token in redis and clear the cookie
    user_id = int(get_jwt_identity())
    jwt_data = get_jwt()
    jti = jwt_data["jti"]

    # revoke token in redis
    revoke_refresh_token(user_id, jti)

    # clear cookie
    resp = make_response(jsonify(msg="Logged out"))
    resp.delete_cookie("refresh_token", path="/refresh")
    return resp

@auth.route("/register", methods=["POST"])
def register():
    # extract stuff
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    email = data.get("email")
    password = data.get("password")

    # you must supply all three
    if not username or not email or not password:
        return jsonify({"msg": "You must supply username, email and password"}), 400

    # check duplicates
    if User.query.filter_by(email=email).first() or User.query.filter_by(user=username).first():
        return jsonify({"msg": "User already registered"}), 409

    # add user to database
    user = User(username, email, hash_password(password))
    db.session.add(user)
    db.session.commit()

    return jsonify({"msg": "Succesfully registered"})
