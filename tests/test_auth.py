# test authentication module
import re
from app.models.user import User
from app.extensions import redis
from flask_jwt_extended import get_csrf_token

JWT_PATTERN = re.compile(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")

def _redis_refresh_keys_for_user(user_id: int):
    pattern = f"refresh:{user_id}:*"
    return list(redis.conn.scan_iter(match=pattern))

def _assert_refresh_cookie_set(resp):
    # verify the refresh token cookie is set with secure attributes
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "refresh_token_cookie=" in set_cookie
    assert "HttpOnly" in set_cookie

def _extract_csrf_from_cookies(client):
    refresh_token_cookie = client.get_cookie("refresh_token_cookie")
    assert refresh_token_cookie is not None
    return get_csrf_token(refresh_token_cookie.decoded_value)

### login success paths

def test_login_success_with_username_sets_cookie_and_redis(client):
    # arrange: register user
    client.post("/register", json={
        "username": "charlie",
        "email": "charlie@example.com",
        "password": "mypass"
    })
    user = User.query.filter_by(user="charlie").first()
    assert user is not None

    # act: login with username
    resp = client.post("/login", json={
        "username": "charlie",
        "password": "mypass"
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

def test_login_success_with_email_sets_cookie_and_redis(client):
    client.post("/register", json={
        "username": "dave",
        "email": "dave@example.com",
        "password": "secret"
    })
    user = User.query.filter_by(user="dave").first()
    assert user is not None

    resp = client.post("/login", json={
        "email": "dave@example.com",
        "password": "secret"
    })
    assert resp.status_code == 200
    body = resp.get_json()
    assert "access_token" in body
    assert JWT_PATTERN.match(body["access_token"])
    _assert_refresh_cookie_set(resp)

    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 1

def test_login_with_both_username_and_email_username_priority(client):
    client.post("/register", json={
        "username": "frank",
        "email": "frank@example.com",
        "password": "abc123"
    })
    user = User.query.filter_by(user="frank").first()
    assert user is not None

    # username should take priority; should still succeed
    resp = client.post("/login", json={
        "username": "frank",
        "email": "wrong@example.com",
        "password": "abc123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.get_json()
    _assert_refresh_cookie_set(resp)

    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 1

### login error paths (and no redis state created)

def test_login_missing_fields(client):
    resp = client.post("/login", json={"username": "nobody"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "missing" in data["msg"].lower()

    # no redis entries should be created for any user
    # (generic check: there should be no refresh:* keys)
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_empty_payload(client):
    resp = client.post("/login", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert "msg" in data and "missing" in data["msg"].lower()
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_invalid_user(client):
    resp = client.post("/login", json={
        "username": "ghost",
        "password": "nope"
    })
    assert resp.status_code == 401
    data = resp.get_json()
    assert "msg" in data and "invalid" in data["msg"].lower()
    any_refresh = list(redis.conn.scan_iter(match="refresh:*"))
    assert len(any_refresh) == 0

def test_login_wrong_password(client):
    client.post("/register", json={
        "username": "erin",
        "email": "erin@example.com",
        "password": "goodpass"
    })
    user = User.query.filter_by(user="erin").first()
    assert user is not None

    resp = client.post("/login", json={
        "username": "erin",
        "password": "badpass"
    })
    assert resp.status_code == 401

    # no redis entry for erin
    keys = _redis_refresh_keys_for_user(user.id)
    assert len(keys) == 0

### end-to-end: login -> refresh

def test_refresh_returns_new_access_token_and_keeps_redis_entry(client):
    # register & login
    client.post("/register", json={
        "username": "hank",
        "email": "hank@example.com",
        "password": "pw123"
    })
    user = User.query.filter_by(user="hank").first()
    assert user is not None

    login_resp = client.post("/login", json={
        "username": "hank",
        "password": "pw123"
    })
    assert login_resp.status_code == 200
    login_body = login_resp.get_json()
    old_access = login_body["access_token"]
    _assert_refresh_cookie_set(login_resp)

    # ensure exactly one refresh token registered in redis
    keys_before = _redis_refresh_keys_for_user(user.id)
    assert len(keys_before) == 1

    # call /refresh (refresh cookie is set automatically by client, but we also
    # need CSRF token in the headers)
    csrf = _extract_csrf_from_cookies(client)
    refresh_resp = client.post("/refresh", headers={"x-csrf-token": csrf})

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

def test_multiple_logins_register_multiple_refresh_entries(client):
    # when logging in multiple times, we expect multiple refresh tokens stored
    client.post("/register", json={
        "username": "multi",
        "email": "multi@example.com",
        "password": "pw"
    })
    user = User.query.filter_by(user="multi").first()
    assert user is not None

    # first login
    r1 = client.post("/login", json={"username": "multi", "password": "pw"})
    assert r1.status_code == 200
    _assert_refresh_cookie_set(r1)
    k1 = set(_redis_refresh_keys_for_user(user.id))
    assert len(k1) == 1

    # second login (new session/refresh cookie + new redis key)
    r2 = client.post("/login", json={"username": "multi", "password": "pw"})
    assert r2.status_code == 200
    _assert_refresh_cookie_set(r2)
    k2 = set(_redis_refresh_keys_for_user(user.id))
    assert len(k2) == 2
    assert k2.issuperset(k1)

### logout tests

def test_logout_revokes_all_tokens_and_clears_cookie(client):
    # register user
    client.post("/register", json={
        "username": "logan",
        "email": "logan@example.com",
        "password": "pw"
    })
    user = User.query.filter_by(user="logan").first()
    assert user is not None

    # login twice to create multiple refresh tokens (multi-session)
    r1 = client.post("/login", json={"username": "logan", "password": "pw"})
    assert r1.status_code == 200
    r2 = client.post("/login", json={"username": "logan", "password": "pw"})
    assert r2.status_code == 200

    # confirm there are >= 2 refresh token entries in Redis
    keys_before = _redis_refresh_keys_for_user(user.id)
    assert len(keys_before) >= 2

    # perform logout with CSRF taken from cookies
    csrf = _extract_csrf_from_cookies(client)
    logout_resp = client.post("/logout", headers={"x-csrf-token": csrf})
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


def test_logout_requires_csrf_token(client):
    # register & login once to set a refresh cookie
    client.post("/register", json={
        "username": "laura",
        "email": "laura@example.com",
        "password": "pw"
    })
    user = User.query.filter_by(user="laura").first()
    assert user is not None

    r = client.post("/login", json={"username": "laura", "password": "pw"})
    assert r.status_code == 200
    assert len(_redis_refresh_keys_for_user(user.id)) == 1

    # attempt logout without CSRF header: should fail with 401
    bad = client.post("/logout")
    assert bad.status_code == 401
