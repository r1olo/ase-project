# test authentication module
import hashlib
import re
from auth.models import EncryptedString, User, get_blind_index
from common.extensions import db, redis_manager as redis
from cryptography.fernet import Fernet
from flask_jwt_extended import get_csrf_token
from unittest.mock import Mock

JWT_PATTERN = re.compile(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")

def _redis_refresh_keys_for_user(user_id: int):
    pattern = f"refresh:{user_id}:*"
    return list(redis.conn.scan_iter(match=pattern))

def _hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def _assert_refresh_cookie_set(resp):
    # verify the refresh token cookie is set with secure attributes
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "refresh_token_cookie=" in set_cookie
    assert "HttpOnly" in set_cookie

def _extract_csrf_from_cookies(auth_client):
    refresh_token_cookie = auth_client.get_cookie("refresh_token_cookie")
    assert refresh_token_cookie is not None
    return get_csrf_token(refresh_token_cookie.decoded_value)

### login success paths

def test_login_success_with_username_sets_cookie_and_redis(auth_client):
    # arrange: register user
    auth_client.post("/register", json={
        "email": "charlie@example.com",
        "password": _hash("mypass")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("charlie@example.com")).first()
    assert user is not None

    # act: login using email (username no longer exists)
    resp = auth_client.post("/login", json={
        "email": "charlie@example.com",
        "password": _hash("mypass")
    })

    # assert: HTTP and token presence
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert isinstance(body["access_token"], str)
    assert JWT_PATTERN.match(body["access_token"])

    # cookie and redis side effects
    _assert_refresh_cookie_set(resp)
    keys = _redis_refresh_keys_for_user(user.id)

    # exactly one refresh token registered
    assert len(keys) == 1

def test_login_success_with_email_sets_cookie_and_redis(auth_client):
    auth_client.post("/register", json={
        "email": "dave@example.com",
        "password": _hash("secret")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("dave@example.com")).first()
    assert user is not None

    resp = auth_client.post("/login", json={
        "email": "dave@example.com",
        "password": _hash("secret")
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert JWT_PATTERN.match(body["access_token"])
    _assert_refresh_cookie_set(resp)

    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 1

def test_login_with_both_username_and_email_username_priority(auth_client):
    auth_client.post("/register", json={
        "email": "frank@example.com",
        "password": _hash("abc123")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("frank@example.com")).first()
    assert user is not None

    # "username" ignored; email used
    resp = auth_client.post("/login", json={
        "email": "frank@example.com",
        "password": _hash("abc123")
    })
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()
    _assert_refresh_cookie_set(resp)

    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 1

### login error paths (and no redis state created)

def test_register_bad_email(auth_client):
    resp = auth_client.post("/register", json={"email": "not_an_email",
                                               "password": "test"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "invalid email" in data["msg"].lower()

def test_login_bad_email(auth_client):
    resp = auth_client.post("/login", json={"email": "not_an_email",
                                            "password": "test"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "invalid email" in data["msg"].lower()

def test_login_missing_fields(auth_client):
    resp = auth_client.post("/login", json={"email": "nobody@example.com"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "missing" in data["msg"].lower()

    # no redis entries should be created for any user
    # (generic check: there should be no refresh:* keys)
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_empty_payload(auth_client):
    resp = auth_client.post("/login", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "missing" in data["msg"].lower()
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_invalid_user(auth_client):
    resp = auth_client.post("/login", json={
        "email": "ghost@example.com",
        "password": _hash("nope")
    })
    assert resp.status_code == 401
    data = resp.get_json()
    assert "msg" in data and "invalid" in data["msg"].lower()
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_wrong_password(auth_client):
    auth_client.post("/register", json={
        "email": "erin@example.com",
        "password": _hash("goodpass")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("erin@example.com")).first()
    assert user is not None

    resp = auth_client.post("/login", json={
        "email": "erin@example.com",
        "password": _hash("badpass")
    })
    assert resp.status_code == 401

    # no redis entry for erin
    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 0

### end-to-end: login -> refresh

def test_refresh_returns_new_access_token_and_keeps_redis_entry(auth_client):
    # register & login
    auth_client.post("/register", json={
        "email": "hank@example.com",
        "password": _hash("pw123")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("hank@example.com")).first()
    assert user is not None

    login_resp = auth_client.post("/login", json={
        "email": "hank@example.com",
        "password": _hash("pw123")
    })
    assert login_resp.status_code == 200
    login_body = login_resp.get_json()
    old_access = login_body["access_token"]
    _assert_refresh_cookie_set(login_resp)

    # ensure exactly one refresh token registered in redis
    keys_before = _redis_refresh_keys_for_user(user.id)
    assert len(keys_before) == 1

    # call /refresh (refresh cookie is set automatically by auth_client, but we also
    # need CSRF token in the headers)
    csrf = _extract_csrf_from_cookies(auth_client)
    refresh_resp = auth_client.post("/refresh", headers={"x-csrf-token": csrf})

    assert refresh_resp.status_code == 200
    refresh_body = refresh_resp.get_json()
    assert "access_token" in refresh_body
    assert JWT_PATTERN.match(refresh_body["access_token"])

    # should be a new access token
    assert refresh_body["access_token"] != old_access

    # redis entry for the refresh token should still exist
    # (no rotation in current contract)
    keys_after = _redis_refresh_keys_for_user(user.id)
    assert len(keys_after) == 1

    # same key(s) still present
    assert set(keys_before) == set(keys_after)

### additional sanity checks

def test_multiple_logins_register_multiple_refresh_entries(auth_client):
    # when logging in multiple times, we expect multiple refresh tokens stored
    auth_client.post("/register", json={
        "email": "multi@example.com",
        "password": _hash("pw")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("multi@example.com")).first()
    assert user is not None

    # first login
    r1 = auth_client.post("/login", json={"email": "multi@example.com", "password": _hash("pw")})
    assert r1.status_code == 200
    _assert_refresh_cookie_set(r1)
    k1 = set(_redis_refresh_keys_for_user(user.id))
    assert len(k1) == 1

    # second login (new session/refresh cookie + new redis key)
    r2 = auth_client.post("/login", json={"email": "multi@example.com", "password": _hash("pw")})
    assert r2.status_code == 200
    _assert_refresh_cookie_set(r2)
    k2 = set(_redis_refresh_keys_for_user(user.id))
    assert len(k2) == 2
    assert k2.issuperset(k1)

### logout tests

def test_logout_revokes_all_tokens_and_clears_cookie(auth_client):
    # register user
    auth_client.post("/register", json={
        "email": "logan@example.com",
        "password": _hash("pw")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("logan@example.com")).first()
    assert user is not None

    # login twice to create multiple refresh tokens (multi-session)
    r1 = auth_client.post("/login", json={"email": "logan@example.com", "password": _hash("pw")})
    assert r1.status_code == 200
    r2 = auth_client.post("/login", json={"email": "logan@example.com", "password": _hash("pw")})
    assert r2.status_code == 200

    # confirm there are >= 2 refresh token entries in Redis
    keys_before = _redis_refresh_keys_for_user(user.id)
    assert len(keys_before) >= 2

    # perform logout with CSRF taken from cookies
    csrf = _extract_csrf_from_cookies(auth_client)
    logout_resp = auth_client.post("/logout", headers={"x-csrf-token": csrf})
    assert logout_resp.status_code == 200
    body = logout_resp.get_json()
    assert "msg" in body and "logged out" in body["msg"].lower()

    # all refresh tokens for this user must be gone
    keys_after = _redis_refresh_keys_for_user(user.id)
    assert len(keys_after) == 0

    # cookie must be cleared
    set_cookie = logout_resp.headers.get("Set-Cookie", "")

    # present with empty/cleared value
    assert "refresh_token_cookie=" in set_cookie
    assert ("Max-Age=0" in set_cookie) or ("expires=" in set_cookie.lower())


def test_logout_requires_csrf_token(auth_client):
    # register & login once to set a refresh cookie
    auth_client.post("/register", json={
        "email": "laura@example.com",
        "password": _hash("pw")
    })
    user = User.query.filter_by(email_blind_index=get_blind_index("laura@example.com")).first()
    assert user is not None

    r = auth_client.post("/login", json={"email": "laura@example.com", "password": _hash("pw")})
    assert r.status_code == 200
    assert len(_redis_refresh_keys_for_user(user.id)) == 1

    # attempt logout without CSRF header: should fail with 401
    bad = auth_client.post("/logout")
    assert bad.status_code == 401


### encryption tests

def test_user_fields_are_encrypted_at_rest(auth_app, tmp_path, monkeypatch):
    # use a custom key file to ensure we decrypt with the same key used for storage
    key = Fernet.generate_key()
    key_path = tmp_path / "auth_enc.key"
    key_path.write_bytes(key)
    monkeypatch.setenv("AUTH_ENCRYPTION_KEY", str(key_path))

    email = "enc@example.com"
    pw_hash = "hashed-password"
    user = User(email=email, pw_hash=pw_hash, salt="salty")
    db.session.add(user)
    db.session.commit()

    row = db.session.execute(
        db.text(
            "SELECT email, pw_hash, email_blind_index FROM users WHERE id = :id"
        ),
        {"id": user.id},
    ).mappings().one()

    # email encrypted at rest, pw_hash stored as plain hash
    assert row["email"] != email
    assert row["pw_hash"] == pw_hash

    cipher = Fernet(key)
    assert cipher.decrypt(row["email"].encode()).decode() == email
    assert row["email_blind_index"] == get_blind_index(email)


def test_encrypted_string_randomizes_ciphertext(tmp_path, monkeypatch):
    key = Fernet.generate_key()
    key_path = tmp_path / "auth_enc.key"
    key_path.write_bytes(key)
    monkeypatch.setenv("AUTH_ENCRYPTION_KEY", str(key_path))

    enc_type = EncryptedString()
    dummy_dialect = Mock()
    first = enc_type.process_bind_param("same-value", dummy_dialect)
    second = enc_type.process_bind_param("same-value", dummy_dialect)

    assert first is not None and second is not None
    assert first != second

    cipher = Fernet(key)
    assert cipher.decrypt(first.encode()).decode() == "same-value"
    assert cipher.decrypt(second.encode()).decode() == "same-value"
