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

def _enqueue_atomic(conn, queue_key, active_key, user_id, max_size):
    """
    Atomically enqueue a user.
    1. If User has an Active Token that is WAITING -> Return it.
    2. If User has an Active Token that is MATCHED -> Generate NEW token, enqueue.
    3. If User has no Active Token -> Generate NEW token, enqueue.
    """
    while True:
        try:
            with conn.pipeline() as pipe:
                pipe.watch(queue_key, active_key)
                
                # Check for an active queue pointer
                existing_token = pipe.hget(active_key, user_id)
                
                if existing_token:
                    # Check the actual status of this token
                    token_status_raw = conn.get(_token_key(existing_token))
                    token_payload = _load_status(token_status_raw)
                    
                    # If explicitly WAITING, return existing (Idempotency)
                    if token_payload and token_payload.get("status") == WAITING:
                        pipe.unwatch()
                        return WAITING, None, existing_token, None

                    # If MATCHED or Expired, we treat them as 'new' for the queue
                    # (The old token remains in Redis with its own TTL for query purposes)

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
                # (Simple logic: if 1+ people waiting, we likely match)
                should_match = queue_len >= 1

                pipe.multi()
                # 1. Update Active Pointer
                pipe.hset(active_key, user_id, new_token)
                # 2. Add to Queue
                pipe.zadd(queue_key, {queue_member: now})
                # 3. Create Status Key (1 hour TTL for waiting)
                _set_token_status(pipe, new_token, _waiting_payload(new_token, now), ttl=3600)

                if should_match:
                    pipe.zpopmin(queue_key, 2)

                results = pipe.execute()

                if should_match:
                    popped = results[-1] # [(member, score), ...]
                    
                    # Handle Match Success
                    if len(popped) == 2:
                        # popped members are "user_id:token"
                        p1_data = popped[0][0].split(":")
                        p2_data = popped[1][0].split(":")
                        
                        players = [p1_data[0], p2_data[0]]
                        tokens = {p1_data[0]: p1_data[1], p2_data[0]: p2_data[1]}
                        
                        return MATCHED, players, new_token, tokens
                    
                    # Edge Case: We popped < 2 (Concurrent race where someone dequeued).
                    # We must re-queue anyone we popped to ensure they don't get lost.
                    if popped:
                        _requeue_popped_atomic(conn, queue_key, popped)
                        # If we are one of them, return Waiting
                        for p in popped:
                            if p[0] == queue_member:
                                return WAITING, None, new_token, None
                
                return WAITING, None, new_token, None

        except WatchError:
            continue

def _requeue_popped_atomic(conn, queue_key, popped_entries):
    """Recover from a failed match pop by putting users back in queue."""
    with conn.pipeline() as pipe:
        for member, score in popped_entries:
            pipe.zadd(queue_key, {member: score})
        pipe.execute()

def _dequeue_atomic(conn, queue_key, active_key, user_id, token_in_query):
    """
    Remove user from queue if and only if the token matches and is WAITING.
    Does NOT remove token if status is MATCHED (returns 'too_late').
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
                pipe.delete(token_k) # Clean up the token key
                
                # Only remove the Active Pointer if it still points to THIS token
                if active_token == token_in_query:
                    pipe.hdel(active_key, user_id)
                
                pipe.execute()
                return "removed"
        except WatchError:
            continue

def _revert_match_failure(conn, queue_key, active_key, player_ids, player_tokens):
    """
    Revert players to queue on Engine Failure.
    CRITICAL: Check if player has re-enqueued (Active Token changed) before reverting.
    If they re-enqueued, DO NOT overwrite their new state; just orphan the failed token.
    If they haven't, put them back in queue with the OLD token.
    """
    timestamp = time.time()
    
    for pid in player_ids:
        old_token = player_tokens[pid]
        old_member = f"{pid}:{old_token}"
        
        while True:
            try:
                with conn.pipeline() as pipe:
                    pipe.watch(active_key)
                    current_active = pipe.hget(active_key, pid)
                    
                    # Case A: User has already re-enqueued (Active token is different)
                    # We do nothing to the Queue or Active Pointer. 
                    if current_active and current_active != old_token:
                        pipe.unwatch()
                        break
                    
                    # Case B: User is still "Active" with this token (or pointer is missing)
                    # We put them back in queue using the OLD token.
                    pipe.multi()
                    pipe.zadd(queue_key, {old_member: timestamp})
                    pipe.hset(active_key, pid, old_token) # Ensure pointer is set
                    _set_token_status(pipe, old_token,
                                      _waiting_payload(old_token, timestamp), ttl=3600)
                    pipe.execute()
                    break
            except WatchError:
                continue

# --- External Interactions ---

def call_game_engine(player_ids):
    """
    Call Game Engine.
    Returns: (response_dict, status_code, is_success_bool)
    """
    # 1. Mock Mode (Testing)
    if current_app.config.get("TESTING", False):
        mock_id = uuid.uuid4().int
        return {"id": mock_id, "status": "mock_started"}, 200, True

    # 2. Real Implementation
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
    
    # Engine returned 4xx or 5xx
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

# TODO: when re-enqueueing with an existing token, return original timestamp
@bp.post("/enqueue")
@jwt_required()
def enqueue():
    conn = _redis()
    user_id = str(get_jwt_identity())

    if not _validate_player_profile(user_id):
        return jsonify({"status": ERROR, "msg": "Profile required"}), 403

    max_size = current_app.config.get("MATCHMAKING_MAX_QUEUE_SIZE")
    
    # Atomic Enqueue
    status_code, players, token, player_tokens = _enqueue_atomic(
        conn, _queue_key(), _active_key(), user_id, max_size
    )

    if status_code == "full":
        return jsonify({"status": ERROR, "msg": "Queue is full"}), 409

    if status_code == MATCHED:
        # Match triggered immediately
        engine_data, http_code, success = call_game_engine(players)
        
        if not success:
            # Handle Failure: Revert players safely
            # Note: We pass the player_tokens map so we know WHICH token to try and revert for each user
            _revert_match_failure(conn, _queue_key(), _active_key(), players, player_tokens)
            return jsonify(_waiting_payload(token)), 200
            
        # Handle Success: Persist 'Matched' status
        assert players is not None
        assert player_tokens is not None
        match_id = engine_data.get("id") or engine_data.get("match_id")
        opponents = {players[0]: players[1], players[1]: players[0]}
        
        with conn.pipeline() as pipe:
            for pid in players:
                tok = player_tokens[pid]
                m_payload = _matched_payload(tok, match_id, opponents[pid])
                # Set TTL to 10 minutes (600s)
                _set_token_status(pipe, tok, m_payload, ttl=600)
                # Clear active pointer (allows re-queuing immediately if they want)
                pipe.hdel(_active_key(), pid)
            pipe.execute()

        # Return response for THIS user
        opponent_id = players[1] if players[0] == user_id else players[0]
        return jsonify(_matched_payload(token, match_id, opponent_id)), 200

    # Default: successfully queued (Waiting)
    return jsonify(_waiting_payload(token)), 202

@bp.get("/status")
@jwt_required()
def status():
    conn = _redis()
    token_in_query = request.args.get("token")
    
    if not token_in_query:
        return jsonify({"status": ERROR, "msg": "Token required"}), 400

    # Direct lookup by token key (Independent of current queue status)
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
    token_in_query = request.args.get("token")

    if not token_in_query:
        return jsonify({"status": ERROR, "msg": "Token required"}), 400

    result = _dequeue_atomic(conn, _queue_key(), _active_key(), user_id, token_in_query)

    if result == "invalid_token":
        return jsonify({"status": ERROR, "msg": "Invalid token"}), 404
    
    if result == "too_late":
        payload_raw = conn.get(_token_key(token_in_query))
        payload = _load_status(payload_raw) or {}
        return jsonify({
            "status": "TooLate",
            "msg": "Match already found",
            "match_id": payload.get("match_id"),
            "opponent_id": payload.get("opponent_id"),
            "queue_token": token_in_query
        }), 409

    return jsonify({"status": "Removed"}), 200
