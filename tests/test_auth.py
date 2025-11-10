# tests/test_auth.py
from app.extensions import db
from app.modules.user import User

def test_register_success(client):
    resp = client.post("/auth/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "secret"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["msg"] == "Succesfully registered"

    # ensure user was saved in DB
    user = User.query.filter_by(email="alice@example.com").first()
    assert user is not None
    assert user.user == "alice"

    # password should be hashed
    assert user.pw_hash != "secret"


def test_register_missing_fields(client):
    resp = client.post("/auth/register", json={"username": "bob"})
    assert resp.status_code == 400
    assert "You must supply" in resp.get_json()["msg"]


def test_register_duplicate_username_or_email(client):
    # first registration
    client.post("/auth/register", json={
        "username": "bob",
        "email": "bob@example.com",
        "password": "1234"
    })

    # duplicate username
    resp = client.post("/auth/register", json={
        "username": "bob",
        "email": "other@example.com",
        "password": "5678"
    })
    assert resp.status_code == 409

    # duplicate email
    resp = client.post("/auth/register", json={
        "username": "otherbob",
        "email": "bob@example.com",
        "password": "5678"
    })
    assert resp.status_code == 409

def test_login_success_with_username(client):
    # first register a user
    client.post("/auth/register", json={
        "username": "charlie",
        "email": "charlie@example.com",
        "password": "mypass"
    })

    # login with username
    resp = client.post("/auth/login", json={
        "username": "charlie",
        "password": "mypass"
    })
    assert resp.status_code == 200
    token = resp.get_json().get("access_token")
    assert token is not None
    assert isinstance(token, str)


def test_login_success_with_email(client):
    # first register a user
    client.post("/auth/register", json={
        "username": "dave",
        "email": "dave@example.com",
        "password": "secret"
    })

    # login with email
    resp = client.post("/auth/login", json={
        "email": "dave@example.com",
        "password": "secret"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()


def test_login_missing_fields(client):
    resp = client.post("/auth/login", json={"username": "nobody"})
    assert resp.status_code == 400
    assert "Missing" in resp.get_json()["msg"]

def test_login_invalid_user(client):
    resp = client.post("/auth/login", json={
        "username": "ghost",
        "password": "nope"
    })
    assert resp.status_code == 401
    assert "Invalid credentials" in resp.get_json()["msg"]


def test_login_wrong_password(client):
    client.post("/auth/register", json={
        "username": "erin",
        "email": "erin@example.com",
        "password": "goodpass"
    })
    resp = client.post("/auth/login", json={
        "username": "erin",
        "password": "badpass"
    })
    assert resp.status_code == 401
