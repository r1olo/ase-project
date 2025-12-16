import json
import time
from flask_jwt_extended import create_access_token
from common.extensions import redis_manager

# --- Helpers ---

def _auth_headers(app, user_id):
    """Helper to generate JWT headers."""
    with app.app_context():
        token = create_access_token(identity=user_id)
    return {"Authorization": f"Bearer {token}"}

class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

def _stub_game_engine(monkeypatch, match_id_start=1, recorded=None):
    """
    Patches `matchmaking.routes.call_game_engine` to return deterministic 
    Match IDs and record the pairs for assertion.
    """
    counter = {"value": match_id_start}

    def fake_call_engine(player_ids):
        match_id = counter["value"]
        counter["value"] += 1
        
        # Record the pair sorted to ensure consistency regardless of who triggered match
        if recorded is not None:
            recorded.append(tuple(sorted(player_ids)))
            
        return {"id": match_id, "status": "started"}, 200, True

    # Patch the helper function directly to bypass internal mock random IDs
    monkeypatch.setattr("matchmaking.routes.call_game_engine", fake_call_engine)

# --- Tests ---

def test_enqueue_first_time_waiting(matchmaking_app, matchmaking_client):
    """Test standard enqueue flow receiving a waiting token."""
    # Use numeric string ID because app casts to int
    headers = _auth_headers(matchmaking_app, "1") 
    resp = matchmaking_client.post("/enqueue", headers=headers)
    
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["status"] == "Waiting"
    assert "queue_token" in data
    
    token = data["queue_token"]
    
    # Verify Redis State
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        active_key = matchmaking_app.config.get("MATCHMAKING_ACTIVE_KEY", "matchmaking:active_pointers")
        
        # User is in ZSet as "1:token"
        assert redis_manager.conn.zcard(queue_key) == 1
        zset_items = redis_manager.conn.zrange(queue_key, 0, -1)
        assert zset_items[0] == f"1:{token}"
        
        # User has active pointer
        assert redis_manager.conn.hget(active_key, "1") == token

        # Token key exists with correct payload
        token_data = json.loads(redis_manager.conn.get(f"matchmaking:token:{token}"))
        assert token_data["status"] == "Waiting"


def test_enqueue_pairs_players_immediately(monkeypatch, matchmaking_app, matchmaking_client):
    """Test that the second player triggers a match and receives matched payload immediately."""
    recorded = []
    _stub_game_engine(monkeypatch, match_id_start=100, recorded=recorded)

    # 1. First player enqueues -> Waiting
    headers_one = _auth_headers(matchmaking_app, "1")
    resp_one = matchmaking_client.post("/enqueue", headers=headers_one)
    assert resp_one.status_code == 202
    token_one = resp_one.get_json()["queue_token"]

    # 2. Second player enqueues -> Matched (Immediate)
    headers_two = _auth_headers(matchmaking_app, "2")
    resp_two = matchmaking_client.post("/enqueue", headers=headers_two)
    
    # Expect 200 OK with Matched payload
    assert resp_two.status_code == 200
    body_two = resp_two.get_json()
    assert body_two["status"] == "Matched"
    assert body_two["match_id"] == 100
    
    # ASSERT INTEGER OPPONENT ID
    assert body_two["opponent_id"] == 1 
    token_two = body_two["queue_token"]

    # 3. Verify Player 1 can poll status to see Match
    resp_status = matchmaking_client.get("/status", headers=headers_one, query_string={"token": token_one})
    assert resp_status.status_code == 200
    status_body = resp_status.get_json()
    assert status_body["status"] == "Matched"
    assert status_body["match_id"] == 100
    
    # ASSERT INTEGER OPPONENT ID
    assert status_body["opponent_id"] == 2 

    # 4. Verify Redis cleanup
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        active_key = matchmaking_app.config.get("MATCHMAKING_ACTIVE_KEY", "matchmaking:active_pointers")
        
        # Queue should be empty (both popped)
        assert redis_manager.conn.zcard(queue_key) == 0
        
        # Active pointers should be removed so they can re-queue immediately
        assert redis_manager.conn.hget(active_key, "1") is None
        assert redis_manager.conn.hget(active_key, "2") is None

        # Tokens should still exist (TTL) with Matched status for polling
        t1_payload = json.loads(redis_manager.conn.get(f"matchmaking:token:{token_one}"))
        assert t1_payload["status"] == "Matched"


def test_idempotent_enqueue_waiting(matchmaking_app, matchmaking_client):
    """If user re-enqueues while waiting, return same token and do NOT duplicate in ZSet."""
    headers = _auth_headers(matchmaking_app, "1")
    
    # First call
    resp1 = matchmaking_client.post("/enqueue", headers=headers)
    token1 = resp1.get_json()["queue_token"]

    # Second call (simulate retry or lost connection)
    resp2 = matchmaking_client.post("/enqueue", headers=headers)
    assert resp2.status_code == 202
    token2 = resp2.get_json()["queue_token"]

    assert token1 == token2

    # Verify only 1 entry in ZSet
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        assert redis_manager.conn.zcard(queue_key) == 1


def test_requeue_after_match_generates_new_token(monkeypatch, matchmaking_app, matchmaking_client):
    """
    User 1 matches User 2. User 1 then enqueues AGAIN.
    Should get a NEW token and be Waiting, while the OLD token remains Matched and queryable.
    """
    _stub_game_engine(monkeypatch, match_id_start=555)

    headers = _auth_headers(matchmaking_app, "1")
    
    # 1. Enqueue -> Wait
    resp1 = matchmaking_client.post("/enqueue", headers=headers)
    token_old = resp1.get_json()["queue_token"]

    # 2. Opponent joins -> Match
    headers_opp = _auth_headers(matchmaking_app, "2")
    matchmaking_client.post("/enqueue", headers=headers_opp)

    # 3. User 1 checks status -> Matched
    resp_stat = matchmaking_client.get("/status", headers=headers, query_string={"token": token_old})
    assert resp_stat.get_json()["status"] == "Matched"

    # 4. User 1 Enqueues AGAIN (New Game Request)
    resp_new = matchmaking_client.post("/enqueue", headers=headers)
    assert resp_new.status_code == 202
    token_new = resp_new.get_json()["queue_token"]

    assert token_new != token_old
    assert resp_new.get_json()["status"] == "Waiting"

    # 5. Verify OLD token is still Matched (for history/polling)
    resp_old_stat = matchmaking_client.get("/status", headers=headers, query_string={"token": token_old})
    assert resp_old_stat.get_json()["status"] == "Matched"

    # 6. Verify NEW token is Waiting
    resp_new_stat = matchmaking_client.get("/status", headers=headers, query_string={"token": token_new})
    assert resp_new_stat.get_json()["status"] == "Waiting"


def test_dequeue_logic_flow(matchmaking_app, matchmaking_client):
    """Test full dequeue lifecycle: Enqueue -> Dequeue -> Cleaned Up."""
    headers = _auth_headers(matchmaking_app, "3")
    
    # 1. Enqueue
    resp_enq = matchmaking_client.post("/enqueue", headers=headers)
    token = resp_enq.get_json()["queue_token"]

    # 2. Dequeue without token -> Error 400
    resp_fail = matchmaking_client.post("/dequeue", headers=headers)
    assert resp_fail.status_code == 400 

    # 3. Dequeue with wrong token -> Error 404
    resp_inv = matchmaking_client.post("/dequeue", headers=headers, json={"token": "bad-token"})
    assert resp_inv.status_code == 404

    # 4. Dequeue with correct token -> Success
    resp_ok = matchmaking_client.post("/dequeue", headers=headers, json={"token": token})
    assert resp_ok.status_code == 200
    assert resp_ok.get_json()["status"] == "Removed"

    # 5. Verify Cleanup
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        active_key = matchmaking_app.config.get("MATCHMAKING_ACTIVE_KEY", "matchmaking:active_pointers")
        
        # Queue empty
        assert redis_manager.conn.zcard(queue_key) == 0
        # Active pointer gone
        assert redis_manager.conn.hget(active_key, "3") is None
        # Token key gone
        assert redis_manager.conn.get(f"matchmaking:token:{token}") is None

def test_dequeue_too_late_matched(monkeypatch, matchmaking_app, matchmaking_client):
    """If user tries to dequeue but was matched in background, return TooLate payload."""
    _stub_game_engine(monkeypatch, match_id_start=99)
    headers = _auth_headers(matchmaking_app, "50")
    
    # 1. User Enqueues
    resp = matchmaking_client.post("/enqueue", headers=headers)
    token = resp.get_json()["queue_token"]

    # 2. Opponent matches them
    headers_opp = _auth_headers(matchmaking_app, "51")
    matchmaking_client.post("/enqueue", headers=headers_opp)

    # 3. User tries to Dequeue -> Too Late
    resp_deq = matchmaking_client.post("/dequeue", headers=headers, json={"token": token})
    assert resp_deq.status_code == 409
    body = resp_deq.get_json()
    assert body["status"] == "TooLate"
    assert body["match_id"] == 99
    assert body["queue_token"] == token
    # Opponent ID should be int
    assert body["opponent_id"] == 51

def test_enqueue_many_odd_count(monkeypatch, matchmaking_app, matchmaking_client):
    """Ensure leftover players stay in queue correctly with correct token format."""
    _stub_game_engine(monkeypatch, match_id_start=50)

    # 7 players -> 3 matches, 1 waiting
    # Using numeric string IDs
    players = [str(i) for i in range(10, 17)] 
    
    for p in players:
        headers = _auth_headers(matchmaking_app, p)
        matchmaking_client.post("/enqueue", headers=headers)

    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        # Should be 1 left
        assert redis_manager.conn.zcard(queue_key) == 1
        
        # The leftover user should be the last one added ("16")
        # Verify the member format is "user_id:token"
        leftover = redis_manager.conn.zrange(queue_key, 0, -1)[0]
        assert leftover.startswith("16:")

def test_enqueue_fails_invalid_profile(monkeypatch, matchmaking_app, matchmaking_client):
    # Patch the validation function to return False
    monkeypatch.setattr("matchmaking.routes._validate_player_profile", lambda uid: False)

    # Use a numeric ID to pass initial parsing logic before validation fails
    headers = _auth_headers(matchmaking_app, "999") 
    resp = matchmaking_client.post("/enqueue", headers=headers)
    
    assert resp.status_code == 403
    assert resp.get_json()["status"] == "Error"
    assert "Profile required" in resp.get_json()["msg"]
