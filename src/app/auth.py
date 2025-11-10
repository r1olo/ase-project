# authentication methods
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from .extensions import bcrypt, db
from .modules.user import User

auth = Blueprint("auth", __name__)

# use bcrypt to generate a password hash
def hash_password(password: str) -> str:
    return bcrypt.generate_password_hash(password).decode("utf-8")

def test_password(password: str, hash: str) -> bool:
    return bcrypt.check_password_hash(hash, password)

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
    if not user:
        return jsonify({"msg": "Invalid credentials"}), 401

    # check supplied password against stored hash
    if not test_password(password, user.pw_hash):
        return jsonify({"msg": "Invalid credentials"}), 401

    # build token and return it
    access_token = create_access_token(identity=username)
    return jsonify(access_token=access_token)

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
