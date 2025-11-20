# http endpoints for matchmaking
import time
import requests
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from redis.exceptions import WatchError
from common.extensions import redis_manager

bp = Blueprint("matchmaking", __name__)

def call_game_engine(player_ids):
    """Create a match in the game engine and handle failures."""
    current_app.logger.info("match found for players %s", player_ids)
    base_url = current_app.config.get("GAME_ENGINE_URL", "http://game-engine:5000").rstrip("/")
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
        _requeue_players_atomic(_redis(), _queue_key(), player_ids)
        return jsonify({"msg": "Game engine unavailable, players re-queued"}), 503

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            data = {"msg": "Match created"}
        return jsonify(data), resp.status_code

    current_app.logger.warning(
        "Game engine failed to create match (%s): %s", resp.status_code, resp.text
    )
    _requeue_players_atomic(_redis(), _queue_key(), player_ids)
    try:
        error_payload = resp.json()
    except ValueError:
        error_payload = {"msg": "Failed to create match"}
    if "msg" not in error_payload:
        error_payload["msg"] = "Failed to create match"
    error_payload["status"] = "requeued"
    return jsonify(error_payload), resp.status_code

# retrieve the redis key for the matchmaking queue
def _queue_key():
    return current_app.config.get("MATCHMAKING_QUEUE_KEY", "matchmaking:queue")

# get the redis connection
def _redis():
    return redis_manager.conn

# run an enqueue operation inside a Redis transaction
def _enqueue_atomic(conn, key, user_id, max_size):
    while True:
        with conn.pipeline() as pipe:
            try:
                pipe.watch(key)
                already_waiting = pipe.zscore(key, user_id)
                queue_len = pipe.zcard(key)
                if (not already_waiting and max_size and max_size > 0
                        and queue_len >= max_size):
                    pipe.unwatch()
                    return "full", None
                queue_after_add = queue_len + (0 if already_waiting else 1)
                should_add = already_waiting is None
                should_match = queue_after_add >= 2
                if not should_add and not should_match:
                    pipe.unwatch()
                    return "waiting", None
                pipe.multi()
                if should_add:
                    pipe.zadd(key, {user_id: time.time()})
                if should_match:
                    pipe.zpopmin(key, 2)
                results = pipe.execute()
                if should_match:
                    popped = results[-1]
                    players = [entry[0] for entry in popped]
                    return "matched", players
                return "waiting", None
            except WatchError:
                continue

def _requeue_players_atomic(conn, key, player_ids):
    """Atomically re-enqueue players if match creation fails."""
    timestamp = time.time()
    with conn.pipeline() as pipe:
        for player_id in player_ids:
            pipe.zadd(key, {player_id: timestamp})
            timestamp += 1e-6  # maintain order for identical timestamps
        pipe.execute()

# enqueue the authenticated user into the matchmaking queue
@bp.post("/enqueue")
@jwt_required()
def enqueue():
    conn = _redis()
    key = _queue_key()
    user_id = str(get_jwt_identity())
    max_size = current_app.config.get("MATCHMAKING_MAX_QUEUE_SIZE")
    status, players = _enqueue_atomic(conn, key, user_id, max_size)
    if status == "full":
        return jsonify({"msg": "Queue is full"}), 409
    if status == "matched" and players:
        return call_game_engine(players)
    return jsonify({"status": "Waiting"}), 202

# dequeue the authenticated user from the matchmaking queue
@bp.post("/dequeue")
@jwt_required()
def dequeue():
    conn = _redis()
    key = _queue_key()
    user_id = str(get_jwt_identity())
    removed = conn.zrem(key, user_id)
    if removed:
        return jsonify({"status": "Removed"}), 200
    return jsonify({"msg": "Player not found in queue"}), 409
