# test authentication module
import re

from flask_jwt_extended import get_csrf_token

from auth.models import User
from common.extensions import redis_manager, db

JWT_PATTERN = re.compile(r"^[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+$")


def _redis_refresh_keys_for_user(user_id: int):
    pattern = f"refresh:{user_id}:*"
    return list(redis_manager.conn.scan_iter(match=pattern))


def _assert_refresh_cookie_set(resp):
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "refresh_token_cookie=" in set_cookie
    assert "HttpOnly" in set_cookie


def _register(auth_client, email="charlie@example.com", password="mypass"):
    resp = auth_client.post("/register", json={"email": email, "password": password})
    assert resp.status_code == 201
    body = resp.get_json()
    return body["user_id"]


def _extract_csrf_from_cookies(client):
    refresh_cookie = client.get_cookie("refresh_token_cookie")
    assert refresh_cookie is not None
    return get_csrf_token(refresh_cookie.decoded_value)


def test_register_requires_email_and_password(auth_client):
    resp = auth_client.post("/register", json={"email": "foo@example.com"})
    assert resp.status_code == 400
    resp = auth_client.post("/register", json={"password": "secret"})
    assert resp.status_code == 400


def test_register_persists_user(auth_client, auth_app):
    user_id = _register(auth_client)
    user = db.session.get(User, user_id)
    assert user is not None
    assert user.email == "charlie@example.com"


def test_login_success_sets_cookie_and_redis(auth_client, auth_app):
    user_id = _register(auth_client)
    resp = auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "mypass"}
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert "access_token" in data and JWT_PATTERN.match(data["access_token"])
    _assert_refresh_cookie_set(resp)
    keys = _redis_refresh_keys_for_user(user_id)
    assert len(keys) == 1


def test_login_missing_fields(auth_client):
    resp = auth_client.post("/login", json={"email": "nobody@example.com"})
    assert resp.status_code == 400


def test_login_invalid_credentials_does_not_touch_redis(auth_client):
    _register(auth_client)
    resp = auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "nope"}
    )
    assert resp.status_code == 401
    assert list(redis_manager.conn.scan_iter(match="refresh:*")) == []


def test_refresh_returns_new_access_token(auth_client):
    _register(auth_client)
    login_resp = auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "mypass"}
    )
    csrf = _extract_csrf_from_cookies(auth_client)
    old_access = login_resp.get_json()["access_token"]

    refresh_resp = auth_client.post("/refresh", headers={"x-csrf-token": csrf})
    assert refresh_resp.status_code == 200
    body = refresh_resp.get_json()
    assert JWT_PATTERN.match(body["access_token"])
    assert body["access_token"] != old_access


def test_refresh_rejects_unknown_token(auth_client):
    _register(auth_client)
    login_resp = auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "mypass"}
    )
    csrf = _extract_csrf_from_cookies(auth_client)
    # wipe redis to simulate revoked token
    redis_manager.conn.flushall()
    resp = auth_client.post("/refresh", headers={"x-csrf-token": csrf})
    assert resp.status_code == 401


def test_logout_revokes_tokens_and_clears_cookie(auth_client):
    user_id = _register(auth_client)
    auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "mypass"}
    )
    auth_client.post(
        "/login", json={"email": "charlie@example.com", "password": "mypass"}
    )
    assert len(_redis_refresh_keys_for_user(user_id)) == 2

    csrf = _extract_csrf_from_cookies(auth_client)
    resp = auth_client.post("/logout", headers={"x-csrf-token": csrf})
    assert resp.status_code == 200
    assert len(_redis_refresh_keys_for_user(user_id)) == 0
    set_cookie = resp.headers.get("Set-Cookie", "")
    assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()
