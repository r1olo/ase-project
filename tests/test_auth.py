# authentication unit tests
from app.models.user import User

def assert_err_resp(resp):
    j = resp.json()
    assert j is not None
    assert "msg" in j

def test_register_success(client):
    # register a new user with valid fields
    resp = client.post("/auth/register", json={
        "username": "alice",
        "email": "alice@example.com",
        "password": "secret"
    })
    assert resp.status_code == 200
    assert_err_resp(resp)

    # ensure user was saved in the database
    user = User.query.filter_by(email="alice@example.com").first()
    assert user is not None
    assert user.user == "alice"

    # ensure password was stored as a hash
    assert user.pw_hash != "secret"

def test_register_missing_fields(client):
    # try registering with missing fields
    resp = client.post("/auth/register", json={"username": "bob"})
    assert resp.status_code == 400
    assert_err_resp(resp)

def test_register_duplicate_username_or_email(client):
    # register first user
    client.post("/auth/register", json={
        "username": "bob",
        "email": "bob@example.com",
        "password": "1234"
    })

    # try registering with duplicate username
    resp = client.post("/auth/register", json={
        "username": "bob",
        "email": "other@example.com",
        "password": "5678"
    })
    assert resp.status_code == 409
    assert_err_resp(resp)

    # try registering with duplicate email
    resp = client.post("/auth/register", json={
        "username": "otherbob",
        "email": "bob@example.com",
        "password": "5678"
    })
    assert resp.status_code == 409
    assert_err_resp(resp)

def test_login_success_with_username(client):
    # register a user
    client.post("/auth/register", json={
        "username": "charlie",
        "email": "charlie@example.com",
        "password": "mypass"
    })

    # login with correct username and password
    resp = client.post("/auth/login", json={
        "username": "charlie",
        "password": "mypass"
    })
    assert resp.status_code == 200
    assert resp.get_json() is not None
    token = resp.get_json().get("access_token")

    # ensure a jwt token was returned
    assert token is not None
    assert isinstance(token, str)

def test_login_success_with_email(client):
    # register a user
    client.post("/auth/register", json={
        "username": "dave",
        "email": "dave@example.com",
        "password": "secret"
    })

    # login using email instead of username
    resp = client.post("/auth/login", json={
        "email": "dave@example.com",
        "password": "secret"
    })
    assert resp.status_code == 200
    assert resp.get_json() is not None
    assert "access_token" in resp.get_json()

def test_login_missing_fields(client):
    # try logging in without a password
    resp = client.post("/auth/login", json={"username": "nobody"})
    assert resp.status_code == 400
    assert_err_resp(resp)

def test_login_invalid_user(client):
    # try logging in with a user that does not exist
    resp = client.post("/auth/login", json={
        "username": "ghost",
        "password": "nope"
    })
    assert resp.status_code == 401
    assert_err_resp(resp)

def test_login_wrong_password(client):
    # register a user
    client.post("/auth/register", json={
        "username": "erin",
        "email": "erin@example.com",
        "password": "goodpass"
    })

    # try logging in with wrong password
    resp = client.post("/auth/login", json={
        "username": "erin",
        "password": "badpass"
    })
    assert resp.status_code == 401
    assert_err_resp(resp)

#########################
# extra edge-case tests #
#########################

def test_register_empty_payload(client):
    # try registering with completely empty json body
    resp = client.post("/auth/register", json={})
    assert resp.status_code == 400
    assert_err_resp(resp)

def test_register_non_json_payload(client):
    # try registering with non-json content type
    resp = client.post("/auth/register", data="not a json")
    assert resp.status_code == 400
    assert_err_resp(resp)

def test_login_empty_payload(client):
    # try logging in with empty json
    resp = client.post("/auth/login", json={})
    assert resp.status_code == 400
    assert_err_resp(resp)

def test_login_with_both_username_and_email(client):
    # register a user
    client.post("/auth/register", json={
        "username": "frank",
        "email": "frank@example.com",
        "password": "abc123"
    })

    # provide both username and email, username should take priority
    resp = client.post("/auth/login", json={
        "username": "frank",
        "email": "wrong@example.com",
        "password": "abc123"
    })
    assert resp.status_code == 200
    assert resp.get_json() is not None
    assert "access_token" in resp.get_json()

def test_register_with_extra_fields(client):
    # register with extra unused fields
    resp = client.post("/auth/register", json={
        "username": "greg",
        "email": "greg@example.com",
        "password": "pass",
        "nickname": "grgr"  # this should be ignored
    })
    assert resp.status_code == 200

def test_login_returns_jwt_identity(client):
    # register and login, then decode jwt to verify identity field
    from flask_jwt_extended import decode_token

    client.post("/auth/register", json={
        "username": "ivan",
        "email": "ivan@example.com",
        "password": "topsecret"
    })
    resp = client.post("/auth/login", json={
        "username": "ivan",
        "password": "topsecret"
    })
    assert resp.status_code == 200
    assert resp.get_json() is not None
    token = resp.get_json()["access_token"]
    assert token is not None

    # decode jwt and ensure identity matches username
    decoded = decode_token(token)
    assert decoded["sub"] == "ivan"
