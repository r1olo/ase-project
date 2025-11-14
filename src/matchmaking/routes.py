# http endpoints for matchmaking
import time
from flask import Blueprint, current_app, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required
from common.extensions import redis_manager

bp = Blueprint("matchmaking", __name__)

# placeholder for integration with the game engine
def call_game_engine(player_ids):
    current_app.logger.info("match found for players %s", player_ids)

# retrieve the redis key for the matchmaking queue
def _queue_key():
    return current_app.config.get("MATCHMAKING_QUEUE_KEY", "matchmaking:queue")

# get the redis connection
def _redis():
    return redis_manager.conn

# pop a full match (two players) from redis or restore entries if incomplete
def _pop_match(conn, key):
    popped = conn.zpopmin(key, 2)
    if len(popped) == 2:
        return [popped[0][0], popped[1][0]]
    for member, score in popped:
        conn.zadd(key, {member: score})
    return None

# enqueue the authenticated user into the matchmaking queue
@bp.post("/enqueue")
@jwt_required()
def enqueue():
    conn = _redis()
    key = _queue_key()
    user_id = str(get_jwt_identity())
    max_size = current_app.config.get("MATCHMAKING_MAX_QUEUE_SIZE")
    already_waiting = conn.zscore(key, user_id) is not None
    if (not already_waiting and max_size and max_size > 0
            and conn.zcard(key) >= max_size):
        return jsonify({"msg": "Queue is full"}), 409
    conn.zadd(key, {user_id: time.time()}, nx=True)
    players = _pop_match(conn, key)
    if players:
        call_game_engine(players)
        return jsonify({"status": "Matched", "players": players}), 200
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
