# https endpoints for matchmaking
import json
import time
import uuid

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from redis.exceptions import WatchError

from common.extensions import redis_manager

bp = Blueprint("matchmaking", __name__)

WAITING = "waiting"
MATCHED = "matched"

def _queue_key():
    """Retrieve the Redis key for the matchmaking queue."""
    return current_app.config.get("MATCHMAKING_QUEUE_KEY", "matchmaking:queue")

def _status_key():
    """Retrieve the Redis key for queue status snapshots."""
    return current_app.config.get("MATCHMAKING_STATUS_KEY") or f"{_queue_key()}:status"

def _redis():
    """Return the Redis connection."""
    return redis_manager.conn

def _load_status(raw):
    """Parse a JSON payload stored in Redis."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _waiting_payload(token, queued_at):
    """Build a status payload for a waiting player."""
    return {
        "status": WAITING,
        "token": token,
        "match_id": None,
        "opponent_id": None,
        "queued_at": queued_at,
        "updated_at": queued_at,
    }

def _matched_payload(token, match_id, opponent_id, queued_at):
    """Build a status payload for a matched player."""
    now = time.time()
    payload = {
        "status": MATCHED,
        "token": token,
        "match_id": match_id,
        "opponent_id": opponent_id,
        "matched_at": now,
        "updated_at": now,
    }
    if queued_at:
        payload["queued_at"] = queued_at
    return payload

def _tokens_for_players(conn, status_key, player_ids):
    """Retrieve queue tokens for a list of players."""
    raw_entries = conn.hmget(status_key, *player_ids)
    tokens = {}
    for player_id, raw in zip(player_ids, raw_entries):
        payload = _load_status(raw)
        if payload and payload.get("token"):
            tokens[player_id] = payload["token"]
    return tokens

def _ensure_tokens(conn, status_key, player_ids, provided=None):
    """Ensure every player has an associated token."""
    tokens = dict(provided or {})
    missing = [pid for pid in player_ids if not tokens.get(pid)]
    if missing:
        stored = _tokens_for_players(conn, status_key, missing)
        tokens.update({pid: tok for pid, tok in stored.items() if tok})
    for pid in player_ids:
        if not tokens.get(pid):
            tokens[pid] = uuid.uuid4().hex
    return tokens

def _store_waiting_statuses(conn, status_key, player_tokens, start_time=None):
    """Persist waiting status snapshots for the given players."""
    timestamp = start_time or time.time()
    with conn.pipeline() as pipe:
        for player_id, token in player_tokens.items():
            pipe.hset(status_key, player_id, json.dumps(_waiting_payload(token, timestamp)))
            timestamp += 1e-6  # keep ordering stable
        pipe.execute()

def _store_matched_statuses(conn, status_key, player_tokens, player_ids, match_id):
    """Persist matched status snapshots for both players."""
    if len(player_ids) != 2:
        return
    opponents = {player_ids[0]: player_ids[1], player_ids[1]: player_ids[0]}
    with conn.pipeline() as pipe:
        for player_id in player_ids:
            existing = _load_status(conn.hget(status_key, player_id))
            queued_at = existing.get("queued_at") if existing else None
            token = player_tokens.get(player_id) or (existing or {}).get("token") or uuid.uuid4().hex
            payload = _matched_payload(token, match_id, opponents[player_id], queued_at)
            pipe.hset(status_key, player_id, json.dumps(payload))
        pipe.execute()

def _enqueue_atomic(conn, queue_key, status_key, user_id, max_size):
    """Run an enqueue operation inside a Redis transaction and return status + metadata."""
    while True:
        with conn.pipeline() as pipe:
            try:
                pipe.watch(queue_key, status_key)
                existing_status = _load_status(pipe.hget(status_key, user_id))
                if (
                    existing_status
                    and existing_status.get("status") == MATCHED
                    and existing_status.get("match_id")
                ):
                    pipe.unwatch()
                    token = existing_status.get("token") or uuid.uuid4().hex
                    return "already_matched", None, token, {user_id: token}, existing_status

                already_waiting = pipe.zscore(queue_key, user_id)
                queue_len = pipe.zcard(queue_key)
                if (not already_waiting and max_size and max_size > 0 and queue_len >= max_size):
                    pipe.unwatch()
                    return "full", None, None, None, existing_status

                token = (existing_status or {}).get("token") or uuid.uuid4().hex
                queue_after_add = queue_len + (0 if already_waiting else 1)
                should_add = already_waiting is None
                should_update_status = existing_status is None or existing_status.get("status") != WAITING
                should_match = queue_after_add >= 2
                if not should_add and not should_match and not should_update_status:
                    pipe.unwatch()
                    return WAITING, None, token, None, existing_status

                now = time.time()
                pipe.multi()
                if should_add:
                    pipe.zadd(queue_key, {user_id: now})
                if should_add or should_update_status:
                    pipe.hset(status_key, user_id, json.dumps(_waiting_payload(token, now)))
                if should_match:
                    pipe.zpopmin(queue_key, 2)
                results = pipe.execute()
                if should_match:
                    popped = results[-1]
                    players = [entry[0] for entry in popped]
                    player_tokens = _ensure_tokens(conn, status_key, players, {user_id: token})
                    return "matched", players, token, player_tokens, existing_status
                return WAITING, None, token, None, existing_status
            except WatchError:
                continue

def _requeue_players_atomic(conn, queue_key, status_key, player_tokens):
    """Atomically re-enqueue players (and refresh their waiting snapshots) if match creation fails."""
    timestamp = time.time()
    with conn.pipeline() as pipe:
        for player_id, token in player_tokens.items():
            pipe.zadd(queue_key, {player_id: timestamp})
            pipe.hset(status_key, player_id, json.dumps(_waiting_payload(token, timestamp)))
            timestamp += 1e-6  # maintain order for identical timestamps
        pipe.execute()

def _lookup_active_match(user_id):
    """Ask the game engine for an active match for this user (used if Redis state was lost)."""
    base_url = current_app.config.get("GAME_ENGINE_URL", "https://game-engine:5000").rstrip("/")
    timeout = current_app.config.get("GAME_ENGINE_REQUEST_TIMEOUT", 3)
    for status in ("SETUP", "IN_PROGRESS"):
        try:
            resp = requests.get(
                f"{base_url}/players/{user_id}/history",
                params={"status": status, "limit": 1},
                timeout=timeout,
            )
        except requests.RequestException as exc:
            current_app.logger.warning("Game engine status lookup failed: %s", exc)
            continue
        if not (200 <= resp.status_code < 300):
            continue
        try:
            payload = resp.json()
        except ValueError:
            continue
        matches = payload.get("matches") or []
        if not matches:
            continue
        match_info = matches[0]
        match_id = match_info.get("id")
        if match_id:
            return {"match_id": match_id, "opponent_id": match_info.get("opponent_id")}
    return None

def call_game_engine(player_ids, player_tokens=None):
    """Create a match in the game engine and handle failures."""
    conn = _redis()
    queue_key = _queue_key()
    status_key = _status_key()
    player_tokens = _ensure_tokens(conn, status_key, player_ids, player_tokens)

    current_app.logger.info("match found for players %s", player_ids)
    base_url = current_app.config.get("GAME_ENGINE_URL", "https://game-engine:5000").rstrip("/")
    timeout = current_app.config.get("GAME_ENGINE_REQUEST_TIMEOUT", 3)

    def _as_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return value

    payload = {
        "player1_id": _as_int(player_ids[0]),
        "player2_id": _as_int(player_ids[1]),
    }

    try:
        resp = requests.post(f"{base_url}/matches/create", json=payload, timeout=timeout)
    except requests.RequestException as exc:
        current_app.logger.error("Game engine unavailable: %s", exc)
        _requeue_players_atomic(conn, queue_key, status_key, player_tokens)
        return jsonify({"msg": "Game engine unavailable, players re-queued"}), 503

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            data = {"msg": "Match created"}
        match_id = data.get("id") or data.get("match_id")
        if match_id:
            _store_matched_statuses(conn, status_key, player_tokens, player_ids, match_id)
        return jsonify(data), resp.status_code

    current_app.logger.warning(
        "Game engine failed to create match (%s): %s", resp.status_code, resp.text
    )
    _requeue_players_atomic(conn, queue_key, status_key, player_tokens)
    try:
        error_payload = resp.json()
    except ValueError:
        error_payload = {"msg": "Failed to create match"}
    if "msg" not in error_payload:
        error_payload["msg"] = "Failed to create match"
    error_payload["status"] = "requeued"
    return jsonify(error_payload), resp.status_code


def _validate_player_profile(user_id):
    """Check if the user has a valid player profile."""
    if current_app.config.get("TESTING"):
        return True

    base_url = current_app.config.get("PLAYERS_URL", "https://players:5000").rstrip("/")
    # Using internal endpoint for validation
    url = f"{base_url}/internal/players/validation"
    
    try:
        resp = requests.post(
            url, 
            json={"user_id": int(user_id)}, 
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("valid", False)
        current_app.logger.warning("Player validation returned status %s", resp.status_code)
        return False
    except requests.RequestException as exc:
        current_app.logger.error("Player service validation failed: %s", exc)
        return False

@bp.post("/enqueue")
@jwt_required()
def enqueue():
    """Enqueue the authenticated user into the matchmaking queue."""
    conn = _redis()
    queue_key = _queue_key()
    status_key = _status_key()
    user_id = str(get_jwt_identity())
    
    # Validation Check
    if not _validate_player_profile(user_id):
        return jsonify({"msg": "You must create a profile first"}), 403

    max_size = current_app.config.get("MATCHMAKING_MAX_QUEUE_SIZE")
    status, players, queue_token, player_tokens, existing_status = _enqueue_atomic(
        conn, queue_key, status_key, user_id, max_size
    )
    if status == "full":
        return jsonify({"msg": "Queue is full"}), 409
    if status == "already_matched" and existing_status:
        public_payload = {
            "status": "Matched",
            "match_id": existing_status.get("match_id"),
            "opponent_id": existing_status.get("opponent_id"),
            "queue_token": existing_status.get("token"),
        }
        return jsonify(public_payload), 200
    if status == "matched" and players:
        return call_game_engine(players, player_tokens)
    return jsonify({"status": "Waiting", "queue_token": queue_token}), 202

@bp.get("/status")
@jwt_required()
def status():
    """Expose polling status for the authenticated user."""
    conn = _redis()
    queue_key = _queue_key()
    status_key = _status_key()
    user_id = str(get_jwt_identity())
    token_filter = request.args.get("token")
    payload = _load_status(conn.hget(status_key, user_id))

    if payload and token_filter and payload.get("token") != token_filter:
        return (
            jsonify({"status": "Stale", "msg": "Provided token does not match active queue entry"}),
            409,
        )

    if payload and payload.get("status") == MATCHED and payload.get("match_id"):
        # delete the cache entry so it is not returned again
        conn.hdel(status_key, user_id)
        return jsonify(
            {
                "status": "Matched",
                "match_id": payload.get("match_id"),
                "opponent_id": payload.get("opponent_id"),
                "queue_token": payload.get("token"),
            }
        ), 200

    if payload and payload.get("status") == WAITING:
        in_queue = conn.zscore(queue_key, user_id) is not None
        return jsonify(
            {
                "status": "Waiting",
                "queue_token": payload.get("token"),
                "in_queue": in_queue,
            }
        ), 200

    # fallback: if Redis lost state, ask the game engine for an active match
    fallback = _lookup_active_match(user_id)
    if fallback:
        return jsonify(
            {
                "status": "Matched",
                "match_id": fallback["match_id"],
                "opponent_id": fallback.get("opponent_id"),
                "source": "game_engine",
            }
        ), 200

    # if the player is still in queue but status was missing, hydrate a fresh waiting snapshot
    in_queue = conn.zscore(queue_key, user_id) is not None
    if in_queue:
        token = uuid.uuid4().hex
        _store_waiting_statuses(conn, status_key, {user_id: token})
        return jsonify({"status": "Waiting", "queue_token": token, "in_queue": True}), 200

    return jsonify({"status": "NotQueued"}), 404

@bp.post("/dequeue")
@jwt_required()
def dequeue():
    """Dequeue the authenticated user from the matchmaking queue."""
    conn = _redis()
    queue_key = _queue_key()
    status_key = _status_key()
    user_id = str(get_jwt_identity())
    status_payload = _load_status(conn.hget(status_key, user_id))
    if status_payload and status_payload.get("status") == MATCHED:
        return jsonify(
            {
                "status": "Matched",
                "match_id": status_payload.get("match_id"),
                "opponent_id": status_payload.get("opponent_id"),
            }
        ), 409

    with conn.pipeline() as pipe:
        pipe.zrem(queue_key, user_id)
        pipe.hdel(status_key, user_id)
        removed, _ = pipe.execute()

    if removed:
        return jsonify({"status": "Removed"}), 200
    return jsonify({"msg": "Player not found in queue"}), 409
