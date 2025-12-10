# test matchmaking microservice
import json
from flask_jwt_extended import create_access_token
from common.extensions import redis_manager

def _auth_headers(app, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    return {"Authorization": f"Bearer {token}"}

class FakeResponse:
    def __init__(self, payload, status_code=201):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

def _stub_game_engine(monkeypatch, match_id_start=1, recorded=None):
    counter = {"value": match_id_start}

    def fake_post(url, json=None, timeout=3):
        player1 = json.get("player1_id")
        player2 = json.get("player2_id")
        match_id = counter["value"]
        counter["value"] += 1
        if recorded is not None:
            recorded.append(
                tuple(
                    sorted(
                        [str(player1), str(player2)],
                        key=lambda pid: int(str(pid).split("-")[-1]),
                    )
                )
            )
        payload = {"id": match_id, "player1_id": player1, "player2_id": player2}
        return FakeResponse(payload, status_code=201)

    monkeypatch.setattr("matchmaking.routes.requests.post", fake_post)

def test_enqueue_pairs_players_when_two_waiting(monkeypatch, matchmaking_app, matchmaking_client):
    _stub_game_engine(monkeypatch, match_id_start=77)
    headers_one = _auth_headers(matchmaking_app, "user-1")
    resp_one = matchmaking_client.post("/enqueue", headers=headers_one)
    assert resp_one.status_code == 202
    token_one = resp_one.get_json()["queue_token"]

    headers_two = _auth_headers(matchmaking_app, "user-2")
    resp_two = matchmaking_client.post("/enqueue", headers=headers_two)
    assert resp_two.status_code == 201
    body = resp_two.get_json()
    assert body["id"] == 77

    # first player can poll and discover the match id
    resp_status = matchmaking_client.get("/status", headers=headers_one, query_string={"token": token_one})
    assert resp_status.status_code == 200
    status_body = resp_status.get_json()
    assert status_body["match_id"] == 77
    assert status_body["opponent_id"] == "user-2"

    # verify cache deletion (delete-on-read)
    resp_status_again = matchmaking_client.get("/status", headers=headers_one, query_string={"token": token_one})
    # depending on fallback logic, it might return 404 NotQueued or 200 Matched (via game engine fallback)
    # But specifically the Redis entry should be gone.
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        status_key = matchmaking_app.config.get("MATCHMAKING_STATUS_KEY", f"{queue_key}:status")
        
        # queue should be empty
        assert redis_manager.conn.zcard(queue_key) == 0
        
        # status entry for user-1 should be deleted
        assert redis_manager.conn.hget(status_key, "user-1") is None

def test_dequeue_removes_player_and_errors_when_missing(matchmaking_app, matchmaking_client):
    headers = _auth_headers(matchmaking_app, "user-3")
    resp_enqueue = matchmaking_client.post("/enqueue", headers=headers)
    assert resp_enqueue.status_code == 202

    resp_leave = matchmaking_client.post("/dequeue", headers=headers)
    assert resp_leave.status_code == 200

    # queue and status entries are gone
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        status_key = matchmaking_app.config.get("MATCHMAKING_STATUS_KEY", f"{queue_key}:status")
        assert redis_manager.conn.zscore(queue_key, "user-3") is None
        assert redis_manager.conn.hget(status_key, "user-3") is None

    resp_missing = matchmaking_client.post("/dequeue", headers=headers)
    assert resp_missing.status_code == 409
    assert "msg" in resp_missing.get_json()

def test_enqueue_many_players_even_count(monkeypatch, matchmaking_app, matchmaking_client):
    recorded = []
    _stub_game_engine(monkeypatch, match_id_start=10, recorded=recorded)

    players = [f"user-{idx}" for idx in range(1, 11)]
    for player in players:
        headers = _auth_headers(matchmaking_app, player)
        matchmaking_client.post("/enqueue", headers=headers)

    assert len(recorded) == len(players) // 2
    assert set(recorded) == {
        ("user-1", "user-2"),
        ("user-3", "user-4"),
        ("user-5", "user-6"),
        ("user-7", "user-8"),
        ("user-9", "user-10"),
    }
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        assert redis_manager.conn.zcard(queue_key) == 0

def test_enqueue_many_players_odd_count(monkeypatch, matchmaking_app, matchmaking_client):
    recorded = []
    _stub_game_engine(monkeypatch, match_id_start=50, recorded=recorded)

    players = [f"user-{idx}" for idx in range(1, 8)]
    for player in players:
        headers = _auth_headers(matchmaking_app, player)
        matchmaking_client.post("/enqueue", headers=headers)

    assert len(recorded) == len(players) // 2
    assert set(recorded) == {
        ("user-1", "user-2"),
        ("user-3", "user-4"),
        ("user-5", "user-6"),
    }
    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        status_key = matchmaking_app.config.get("MATCHMAKING_STATUS_KEY", f"{queue_key}:status")
        waiting = redis_manager.conn.zrange(queue_key, 0, -1)
        assert waiting == ["user-7"]
        status_payload = redis_manager.conn.hget(status_key, "user-7")
        assert status_payload is not None
