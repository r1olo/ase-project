import json
import time
import uuid

import requests
from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from redis.exceptions import WatchError

from common.extensions import redis_manager

bp = Blueprint("matchmaking", __name__)

WAITING = "Waiting"
MATCHED = "Matched"
ERROR = "Error"

# --- Redis Configuration ---

def _queue_key():
    return current_app.config.get("MATCHMAKING_QUEUE_KEY", "matchmaking:queue")

def _active_key():
    """Hash mapping user_id -> current_queue_token."""
    return current_app.config.get("MATCHMAKING_ACTIVE_KEY", "matchmaking:active_pointers")

def _token_key(token):
    """Key for a specific token's payload."""
    return f"matchmaking:token:{token}"

def _redis():
    return redis_manager.conn

def _load_status(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None

# --- Payload Builders ---

def _waiting_payload(token, queued_at=None):
    return {
        "status": WAITING,
        "queue_token": token,
        "queued_at": queued_at or time.time(),
    }

def _matched_payload(token, match_id, opponent_id):
    return {
        "status": MATCHED,
        "queue_token": token,
        "match_id": match_id,
        "opponent_id": opponent_id,
    }

# --- Atomic Operations ---

def _set_token_status(pipe, token, payload, ttl=3600):
    """Helper to set token payload with expiry in a pipeline."""
    pipe.setex(_token_key(token), ttl, json.dumps(payload))

def _safely_requeue_user(conn, queue_key, active_key, user_id, token, score):
    """
    ATOMIC HELPER: Puts user back in queue ONLY if they haven't cancelled.
    
    This fixes the 'Zombie' race condition. If a user dequeues (cancels)
    during the microsecond they were popped from the queue, their Active Pointer
    will be gone or different. We must check this before putting them back.
    
    Args:
        score: The original timestamp. Passing this ensures we preserve 
               queue fairness (they keep their spot in line).
    """
    queue_member = f"{user_id}:{token}"
    
    while True:
        try:
            with conn.pipeline() as pipe:
                pipe.watch(active_key)
                
                # Check: Is this specific token still the active one?
                current_active = pipe.hget(active_key, user_id)
                
                if current_active == token:
                    # User is still valid. Re-insert at ORIGINAL score.
                    pipe.multi()
                    pipe.zadd(queue_key, {queue_member: score})
                    
                    # Refresh the status key TTL just in case
                    _set_token_status(pipe, token, _waiting_payload(token, score), ttl=3600)
                    
                    pipe.execute()
                else:
                    # User cancelled (pointer gone) or re-queued (pointer changed).
                    # Do nothing. Drop this 'zombie' entry.
                    pipe.unwatch()
                return
        except WatchError:
            continue

def _requeue_popped_atomic(conn, queue_key, active_key, popped_entries):
    """
    Recover from a failed match pop (ZPOPMIN) by putting users back.
    Wraps _safely_requeue_user to handle list processing.
    """
    for member, score in popped_entries:
        user_id = member.split(":")[0]
        token = member.split(":")[1]
        
        # Uses the Score from the pop to preserve position
        _safely_requeue_user(conn, queue_key, active_key, user_id, token, score)

def _revert_match_failure(conn, queue_key, active_key, player_ids, player_tokens):
    """
    Revert players to queue on Engine Failure (HTTP 500).
    Now attempts to recover the original timestamp for fairness.
    """
    for pid in player_ids:
        token = player_tokens[pid]
        original_score = time.time() # Default fallback (unfair)

        # 1. Try to fetch original queue time from the token payload
        # This ensures that if the engine fails, users don't lose their spot.
        try:
            raw_payload = conn.get(_token_key(token))
            payload = _load_status(raw_payload)
            if payload and payload.get("queued_at"):
                original_score = float(payload["queued_at"])
        except Exception:
            pass # Keep fallback time

        # 2. Requeue safely
        _safely_requeue_user(conn, queue_key, active_key, pid, token, original_score)

def _enqueue_atomic(conn, queue_key, active_key, user_id, max_size):
    """
    Atomically enqueue a user.
    """
    while True:
        try:
            with conn.pipeline() as pipe:
                pipe.watch(queue_key, active_key)
                
                # Check for an active queue pointer
                existing_token = pipe.hget(active_key, user_id)
                
                if existing_token:
                    # Check status of existing token
                    token_status_raw = conn.get(_token_key(existing_token))
                    token_payload = _load_status(token_status_raw)
                    
                    # If explicitly WAITING, return existing (Idempotency)
                    if token_payload and token_payload.get("status") == WAITING:
                        pipe.unwatch()
                        return WAITING, None, existing_token, None

                # Check queue limit
                queue_len = pipe.zcard(queue_key)
                if max_size and max_size > 0 and queue_len >= max_size:
                    pipe.unwatch()
                    return "full", None, None, None

                # Generate NEW token
                new_token = uuid.uuid4().hex
                now = time.time()
                queue_member = f"{user_id}:{new_token}"

                # Optimization: Check if this addition triggers a match
                should_match = queue_len >= 1

                pipe.multi()
                # 1. Update Active Pointer
                pipe.hset(active_key, user_id, new_token)
                # 2. Add to Queue
                pipe.zadd(queue_key, {queue_member: now})
                # 3. Create Status Key
                _set_token_status(pipe, new_token, _waiting_payload(new_token, now), ttl=3600)

                if should_match:
                    pipe.zpopmin(queue_key, 2)

                results = pipe.execute()

                if should_match:
                    popped = results[-1] # [(member, score), ...]
                    
                    # Handle Match Success
                    if len(popped) == 2:
                        p1_data = popped[0][0].split(":")
                        p2_data = popped[1][0].split(":")
                        
                        players = [p1_data[0], p2_data[0]]
                        tokens = {p1_data[0]: p1_data[1], p2_data[0]: p2_data[1]}
                        
                        return MATCHED, players, new_token, tokens
                    
                    # Handle Failed Pop (Race condition)
                    if popped:
                        _requeue_popped_atomic(conn, queue_key, active_key, popped)
                        
                        # If we were one of them, we are Waiting
                        for p in popped:
                            if p[0] == queue_member:
                                return WAITING, None, new_token, None
                
                return WAITING, None, new_token, None

        except WatchError:
            continue

def _dequeue_atomic(conn, queue_key, active_key, user_id, token_in_query):
    """
    Remove user from queue if and only if the token matches and is WAITING.
    """
    token_k = _token_key(token_in_query)
    
    while True:
        try:
            with conn.pipeline() as pipe:
                pipe.watch(active_key, token_k)
                
                status_raw = pipe.get(token_k)
                payload = _load_status(status_raw)

                # 1. Invalid Token
                if not payload:
                    pipe.unwatch()
                    return "invalid_token"
                
                # 2. Already Matched
                if payload.get("status") == MATCHED:
                    pipe.unwatch()
                    return "too_late"

                # 3. Waiting - Attempt Removal
                queue_member = f"{user_id}:{token_in_query}"
                active_token = pipe.hget(active_key, user_id)

                pipe.multi()
                pipe.zrem(queue_key, queue_member)
                pipe.delete(token_k) 
                
                # Only remove the Active Pointer if it still points to THIS token
                if active_token == token_in_query:
                    pipe.hdel(active_key, user_id)
                
                pipe.execute()
                return "removed"
        except WatchError:
            continue

# --- External Interactions ---

def call_game_engine(player_ids):
    """
    Call Game Engine.
    Returns: (response_dict, status_code, is_success_bool)
    """
    if current_app.config.get("TESTING", False):
        mock_id = uuid.uuid4().int
        return {"id": mock_id, "status": "mock_started"}, 200, True

    base_url = current_app.config.get("GAME_ENGINE_URL", "https://game-engine:5000").rstrip("/")
    timeout = current_app.config.get("GAME_ENGINE_REQUEST_TIMEOUT", 3)
    payload = {"player1_id": int(player_ids[0]), "player2_id": int(player_ids[1])}

    try:
        resp = requests.post(
            f"{base_url}/internal/matches/create",
            json=payload,
            timeout=timeout,
            verify=current_app.config.get("MATCHMAKING_ENABLE_VERIFY", False)
        )
    except requests.RequestException as exc:
        current_app.logger.error("Game engine unavailable: %s", exc)
        return {"msg": "Game engine unavailable"}, 503, False

    if 200 <= resp.status_code < 300:
        try:
            data = resp.json()
        except ValueError:
            data = {"id": None}
        return data, resp.status_code, True
    
    current_app.logger.error("Game engine error: %s", resp.text)
    return {"msg": "Failed to create match"}, resp.status_code, False


def _validate_player_profile(user_id):
    if current_app.config.get("TESTING"): return True
    base_url = current_app.config.get("PLAYERS_URL", "https://players:5000").rstrip("/")
    try:
        resp = requests.post(f"{base_url}/internal/players/validation",
            json={"user_id": int(user_id)},
            timeout=3,
            verify=current_app.config.get("MATCHMAKING_ENABLE_VERIFY", False))
        return resp.json().get("valid", False) if resp.status_code == 200 else False
    except requests.RequestException:
        return False

# --- API Routes ---

@bp.post("/enqueue")
@jwt_required()
def enqueue():
    conn = _redis()
    user_id = str(get_jwt_identity())

    if not _validate_player_profile(user_id):
        return jsonify({"status": ERROR, "msg": "Profile required"}), 403

    max_size = current_app.config.get("MATCHMAKING_MAX_QUEUE_SIZE")
    
    status_code, players, token, player_tokens = _enqueue_atomic(
        conn, _queue_key(), _active_key(), user_id, max_size
    )

    if status_code == "full":
        return jsonify({"status": ERROR, "msg": "Queue is full"}), 409

    if status_code == MATCHED:
        # Match triggered immediately
        engine_data, http_code, success = call_game_engine(players)
        
        if not success:
            # Handle Failure: Revert players safely using the new atomic helper
            _revert_match_failure(conn, _queue_key(), _active_key(), players, player_tokens)
            return jsonify(_waiting_payload(token)), 200
            
        # Handle Success
        assert players is not None
        assert player_tokens is not None
        match_id = engine_data.get("id") or engine_data.get("match_id")
        opponents = {players[0]: players[1], players[1]: players[0]}
        
        with conn.pipeline() as pipe:
            for pid in players:
                tok = player_tokens[pid]
                m_payload = _matched_payload(tok, match_id, int(opponents[pid]))
                # Set TTL to 10 minutes
                _set_token_status(pipe, tok, m_payload, ttl=600)
                # Clear active pointer (allows re-queuing immediately if they want)
                pipe.hdel(_active_key(), pid)
            pipe.execute()

        # Return response for THIS user
        opponent_id = players[1] if players[0] == user_id else players[0]
        return jsonify(_matched_payload(token, match_id, int(opponent_id))), 200

    # Default: successfully queued (Waiting)
    return jsonify(_waiting_payload(token)), 202

@bp.get("/status")
@jwt_required()
def status():
    conn = _redis()
    token_in_query = request.args.get("token")
    
    if not token_in_query:
        return jsonify({"status": ERROR, "msg": "Token required"}), 400

    payload_raw = conn.get(_token_key(token_in_query))
    payload = _load_status(payload_raw)

    if not payload:
        return jsonify({"status": ERROR, "msg": "Invalid token"}), 404

    return jsonify(payload), 200

@bp.post("/dequeue")
@jwt_required()
def dequeue():
    conn = _redis()
    user_id = str(get_jwt_identity())
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")

    if token is None:
        return jsonify({"status": ERROR, "msg": "Token required"}), 400

    result = _dequeue_atomic(conn, _queue_key(), _active_key(), user_id, token)

    if result == "invalid_token":
        return jsonify({"status": ERROR, "msg": "Invalid token"}), 404
    
    if result == "too_late":
        payload_raw = conn.get(_token_key(token))
        payload = _load_status(payload_raw) or {}
        return jsonify({
            "status": "TooLate",
            "msg": "Match already found",
            "match_id": payload.get("match_id"),
            "opponent_id": payload.get("opponent_id"),
            "queue_token": token
        }), 409

    return jsonify({"status": "Removed"}), 200
