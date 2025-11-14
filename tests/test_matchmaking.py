# test matchmaking microservice
from flask_jwt_extended import create_access_token
from common.extensions import redis_manager

# build authorization headers for a fake user
def _auth_headers(app, user_id):
    with app.app_context():
        token = create_access_token(identity=user_id)
    return {"Authorization": f"Bearer {token}"}

# sort player ids numerically to ease assertions
def _sorted_pair(player_ids):
    return tuple(sorted(player_ids, key=lambda pid: int(pid.split("-")[1])))

# ensure players are paired and the game engine callback is invoked
def test_enqueue_pairs_players_when_two_waiting(monkeypatch, matchmaking_app, matchmaking_client):
    recorded_matches = []

    def fake_call(player_ids):
        recorded_matches.append(player_ids)

    monkeypatch.setattr("matchmaking.routes.call_game_engine", fake_call)
    headers_one = _auth_headers(matchmaking_app, "user-1")
    resp_one = matchmaking_client.post("/enqueue", headers=headers_one)
    assert resp_one.status_code == 202

    headers_two = _auth_headers(matchmaking_app, "user-2")
    resp_two = matchmaking_client.post("/enqueue", headers=headers_two)
    assert resp_two.status_code == 200
    body = resp_two.get_json()
    assert sorted(body["players"]) == ["user-1", "user-2"]
    assert recorded_matches and sorted(recorded_matches[0]) == ["user-1", "user-2"]

    with matchmaking_app.app_context():
        queue_key = matchmaking_app.config["MATCHMAKING_QUEUE_KEY"]
        assert redis_manager.conn.zcard(queue_key) == 0

# ensure dequeue works and errors if the player was already matched or removed
def test_dequeue_removes_player_and_errors_when_missing(matchmaking_app, matchmaking_client):
    headers = _auth_headers(matchmaking_app, "user-3")
    resp_enqueue = matchmaking_client.post("/enqueue", headers=headers)
    assert resp_enqueue.status_code == 202

    resp_leave = matchmaking_client.post("/dequeue", headers=headers)
    assert resp_leave.status_code == 200

    resp_missing = matchmaking_client.post("/dequeue", headers=headers)
    assert resp_missing.status_code == 409
    assert "msg" in resp_missing.get_json()

# ensure an even batch of players forms the expected number of matches
def test_enqueue_many_players_even_count(monkeypatch, matchmaking_app, matchmaking_client):
    recorded = []

    def fake_call(player_ids):
        recorded.append(_sorted_pair(player_ids))

    monkeypatch.setattr("matchmaking.routes.call_game_engine", fake_call)
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

# ensure an odd batch of players leaves one player in queue
def test_enqueue_many_players_odd_count(monkeypatch, matchmaking_app, matchmaking_client):
    recorded = []

    def fake_call(player_ids):
        recorded.append(_sorted_pair(player_ids))

    monkeypatch.setattr("matchmaking.routes.call_game_engine", fake_call)
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
        waiting = redis_manager.conn.zrange(queue_key, 0, -1)
        assert waiting == ["user-7"]
