import pytest
from unittest.mock import patch, MagicMock
from flask_jwt_extended import create_access_token

# Import actual constants to ensure tests stay in sync with logic
from game_engine.game_engine import MAX_ROUNDS

# --- FIXTURES ---

@pytest.fixture
def app(game_engine_app):
    return game_engine_app

@pytest.fixture
def client(game_engine_client):
    return game_engine_client

@pytest.fixture
def auth_headers(app):
    """Generates valid JWT headers for a given user_id."""
    def _make_headers(user_id):
        with app.app_context():
            token = create_access_token(identity=str(user_id))
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    return _make_headers

@pytest.fixture
def mock_catalogue_data():
    """Raw card data simulating the Catalogue database."""
    return [
        {
            "id": i,
            "name": f"Card {i}",
            "economy": 10,
            "food": 10,
            "environment": 10,
            "special": 10,
            "total": 40.0
        } for i in range(1, 100)
    ]

# --- HELPERS ---

def setup_active_match(client, auth_headers, mock_catalogue_data):
    """Helper to create a match and submit decks to reach IN_PROGRESS state."""
    # 1. Create match
    m_resp = client.post('/matches/create', json={"player1_id": 10, "player2_id": 20})
    match_id = m_resp.json['id']
    
    deck_ids = [1, 2, 3, 4, 5]
    
    # Mock side_effect: filters the 'DB' to return only cards requested in the JSON body
    def side_effect(*args, **kwargs):
        json_body = kwargs.get('json', {})
        requested_ids = json_body.get('data', [])
        filtered = [c for c in mock_catalogue_data if c['id'] in requested_ids]
        
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"data": filtered}
        return mock

    # 2. Submit decks using the smart mock
    with patch('game_engine.services.requests.post', side_effect=side_effect):
        client.post(f'/matches/{match_id}/deck', headers=auth_headers(10), json={"data": deck_ids})
        client.post(f'/matches/{match_id}/deck', headers=auth_headers(20), json={"data": deck_ids})
    
    return match_id

# --- TESTS ---

def test_health_check(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok"}

def test_create_match_success(client):
    response = client.post('/matches/create', json={"player1_id": 1, "player2_id": 2})
    assert response.status_code == 201
    assert response.json['status'] == 'SETUP'

def test_choose_deck_success(client, auth_headers, mock_catalogue_data):
    """Verifies valid deck submission keeps match in SETUP (waiting for P2)."""
    m_resp = client.post('/matches/create', json={"player1_id": 10, "player2_id": 20})
    match_id = m_resp.json['id']
    deck_ids = [1, 2, 3, 4, 5]
    
    def side_effect(*args, **kwargs):
        json_body = kwargs.get('json', {})
        requested = json_body.get('data', [])
        filtered = [c for c in mock_catalogue_data if c['id'] in requested]
        
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"data": filtered}
        return mock

    with patch('game_engine.services.requests.post', side_effect=side_effect):
        response = client.post(
            f'/matches/{match_id}/deck',
            headers=auth_headers(10),
            json={"data": deck_ids}
        )
    
    assert response.status_code == 200
    assert response.json['status'] == 'SETUP'

def test_choose_deck_starts_match(client, auth_headers, mock_catalogue_data):
    """Verifies match transitions to IN_PROGRESS after both players submit decks."""
    m_resp = client.post('/matches/create', json={"player1_id": 10, "player2_id": 20})
    match_id = m_resp.json['id']
    deck_ids = [1, 2, 3, 4, 5]

    def side_effect(*args, **kwargs):
        json_body = kwargs.get('json', {})
        requested = json_body.get('data', [])
        filtered = [c for c in mock_catalogue_data if c['id'] in requested]
        
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"data": filtered}
        return mock

    with patch('game_engine.services.requests.post', side_effect=side_effect):
        client.post(f'/matches/{match_id}/deck', headers=auth_headers(10), json={"data": deck_ids})
        resp = client.post(f'/matches/{match_id}/deck', headers=auth_headers(20), json={"data": deck_ids})

    assert resp.status_code == 200
    assert resp.json['status'] == 'IN_PROGRESS'

def test_submit_move_flow(client, auth_headers, mock_catalogue_data):
    """Verifies turn-based flow: P1 waits, P2 triggers round processing."""
    match_id = setup_active_match(client, auth_headers, mock_catalogue_data)
    
    # Player 1 submits -> Wait
    p1_resp = client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(10), json={"card_id": 1})
    assert p1_resp.status_code == 200
    assert p1_resp.json['status'] == 'WAITING_FOR_OPPONENT'
    
    # Player 2 submits -> Round End
    p2_resp = client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(20), json={"card_id": 2})
    assert p2_resp.status_code == 200
    assert p2_resp.json['status'] == 'ROUND_PROCESSED'
    assert p2_resp.json['next_round'] == 2

def test_submit_invalid_card(client, auth_headers, mock_catalogue_data):
    """Verifies rejection when playing a card not in the player's deck."""
    match_id = setup_active_match(client, auth_headers, mock_catalogue_data)
    
    # Deck only contains 1-5; try playing 99
    response = client.post(
        f'/matches/{match_id}/moves/1', 
        headers=auth_headers(10), 
        json={"card_id": 99}
    )
    
    assert response.status_code == 400
    assert "not in the player's deck" in response.json['msg']

def test_submit_duplicate_move_round(client, auth_headers, mock_catalogue_data):
    """Verifies a player cannot submit multiple moves for the same round."""
    match_id = setup_active_match(client, auth_headers, mock_catalogue_data)
    
    # First move ok
    client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(10), json={"card_id": 1})
    
    # Duplicate move fails
    response = client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(10), json={"card_id": 2})
    
    assert response.status_code == 400
    assert "already submitted" in response.json['msg']

def test_submit_played_card(client, auth_headers, mock_catalogue_data):
    """Verifies cards cannot be reused in subsequent rounds."""
    match_id = setup_active_match(client, auth_headers, mock_catalogue_data)
    
    # Round 1: Both play card 1
    client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(10), json={"card_id": 1})
    client.post(f'/matches/{match_id}/moves/1', headers=auth_headers(20), json={"card_id": 1})
    
    # Round 2: P1 tries card 1 again
    response = client.post(f'/matches/{match_id}/moves/2', headers=auth_headers(10), json={"card_id": 1})
    
    assert response.status_code == 400
    assert "already been played" in response.json['msg']

def test_game_completion_and_history(client, auth_headers, mock_catalogue_data):
    """Verifies the match finishes after MAX_ROUNDS and history is updated."""
    match_id = setup_active_match(client, auth_headers, mock_catalogue_data)
    
    # Play all rounds
    for i in range(1, MAX_ROUNDS + 1):
        # Mocks not needed here as moves are internal logic
        client.post(f'/matches/{match_id}/moves/{i}', headers=auth_headers(10), json={"card_id": i})
        client.post(f'/matches/{match_id}/moves/{i}', headers=auth_headers(20), json={"card_id": i})

    # Verify history
    resp = client.get(f'/matches/history/10', headers=auth_headers(10))
    assert resp.status_code == 200
    
    match_entry = next(m for m in resp.json['matches'] if m['id'] == match_id)
    assert match_entry['status'] == 'FINISHED'

def test_leaderboard(client, auth_headers):
    resp = client.get('/leaderboard', headers=auth_headers(1))
    assert resp.status_code == 200
    assert 'leaderboard' in resp.json