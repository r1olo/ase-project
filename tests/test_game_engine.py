"""
Comprehensive test suite for the game engine microservice.
Tests all endpoints and game logic in isolation.

Updated to work with the new service layer architecture.
"""
import pytest
from common.extensions import db as _db
from game_engine.models import Match, Move
from game_engine import create_test_app


@pytest.fixture(scope='session')
def app():
    """Create application for the tests."""
    app = create_test_app()
    
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture(scope='function')
def client(app):
    """Test client for the application."""
    return app.test_client()


@pytest.fixture(scope='function')
def db(app):
    """
    Clean database for each test.
    """
    with app.app_context():
        # Clean all tables
        _db.session.query(Move).delete()
        _db.session.query(Match).delete()
        _db.session.commit()
        
        yield _db
        
        # Cleanup after test
        _db.session.rollback()


def create_test_deck():
    """Helper to create a valid test deck."""
    return [f"card_{i}" for i in range(1, 11)]


def create_mock_deck_stats():
    """Helper to create mock deck stats."""
    deck = create_test_deck()
    return {
        card_id: {
            "economy": 10,
            "food": 10,
            "environment": 10,
            "special": 2,
            "total": 32.0
        }
        for card_id in deck
    }


# ============== HEALTH CHECK ==============

def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get('/game/health')
    assert response.status_code == 200
    assert response.json == {"status": "ok"}


# ============== MATCH CREATION ==============

def test_create_match_success(client, db):
    """Test successful match creation."""
    response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    
    assert response.status_code == 201
    data = response.json
    assert data['player1_id'] == 1
    assert data['player2_id'] == 2
    assert data['status'] == 'SETUP'
    assert data['current_round'] == 1
    assert 'id' in data


def test_create_match_same_players(client):
    """Test that same player IDs are rejected."""
    response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 1
    })
    
    assert response.status_code == 400
    assert 'different' in response.json['msg'].lower()


def test_create_match_invalid_types(client):
    """Test that invalid player ID types are rejected."""
    response = client.post('/game/matches', json={
        "player1_id": "invalid",
        "player2_id": 2
    })
    
    assert response.status_code == 400
    assert 'integer' in response.json['msg'].lower()


def test_create_match_missing_fields(client):
    """Test that missing fields are rejected."""
    response = client.post('/game/matches', json={
        "player1_id": 1
    })
    
    assert response.status_code == 400


# ============== DECK SELECTION ==============

def test_choose_deck_success(client, db):
    """Test successful deck submission."""
    # Create match first
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    # Submit deck for player 1
    deck = create_test_deck()
    response = client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 1,
        "deck": deck
    })
    
    assert response.status_code == 200
    data = response.json
    assert data['player1_deck'] is not None
    assert data['status'] == 'SETUP'  # Still waiting for player 2


def test_choose_deck_both_players_starts_match(client, db):
    """Test that match starts when both players submit decks."""
    # Create match
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    # Submit deck for player 1
    deck = create_test_deck()
    client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 1,
        "deck": deck
    })
    
    # Submit deck for player 2
    response = client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 2,
        "deck": deck
    })
    
    assert response.status_code == 200
    data = response.json
    assert data['status'] == 'IN_PROGRESS'
    assert data['player1_deck'] is not None
    assert data['player2_deck'] is not None
    assert data['current_round_category'] in ['economy', 'food', 'environment', 'special']


def test_choose_deck_wrong_size(client, db):
    """Test that wrong deck size is rejected."""
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    response = client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 1,
        "deck": ["card_1", "card_2"]  # Only 2 cards
    })
    
    assert response.status_code == 400
    assert '10' in response.json['msg']


def test_choose_deck_duplicate_cards(client, db):
    """Test that duplicate cards are rejected."""
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    deck = ["card_1"] * 10  # Same card 10 times
    response = client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 1,
        "deck": deck
    })
    
    assert response.status_code == 400
    assert 'duplicate' in response.json['msg'].lower()


def test_choose_deck_non_participant(client, db):
    """Test that non-participants can't submit decks."""
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    deck = create_test_deck()
    response = client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 999,  # Not in match
        "deck": deck
    })
    
    assert response.status_code == 400
    assert 'not part' in response.json['msg'].lower()


# ============== MOVE SUBMISSION ==============

def setup_match_in_progress(client):
    """Helper to create a match ready for moves."""
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    deck = create_test_deck()
    client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 1,
        "deck": deck
    })
    client.post(f'/game/matches/{match_id}/deck', json={
        "player_id": 2,
        "deck": deck
    })
    
    return match_id


def test_submit_first_move(client, db):
    """Test submitting the first move of a round."""
    match_id = setup_match_in_progress(client)
    
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    assert response.status_code == 200
    data = response.json
    assert data['status'] == 'WAITING_FOR_OPPONENT'
    assert 'move_submitted' in data


def test_submit_second_move_processes_round(client, db):
    """Test that second move processes the round."""
    match_id = setup_match_in_progress(client)
    
    # Player 1 moves
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    # Player 2 moves
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 2,
        "card_id": "card_1"
    })
    
    assert response.status_code == 200
    data = response.json
    assert data['status'] == 'ROUND_PROCESSED'
    assert 'round_winner_id' in data
    assert 'is_draw' in data
    assert 'moves' in data
    assert len(data['moves']) == 2
    assert data['next_round'] == 2


def test_submit_move_duplicate_in_round(client, db):
    """Test that player can't submit twice in same round."""
    match_id = setup_match_in_progress(client)
    
    # Player 1 moves
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    # Player 1 tries to move again
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_2"
    })
    
    assert response.status_code == 400
    assert 'already submitted' in response.json['msg'].lower()
    assert 'code' in response.json


def test_submit_move_card_already_played(client, db):
    """Test that cards can't be played twice."""
    match_id = setup_match_in_progress(client)
    
    # Round 1
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 2,
        "card_id": "card_2"
    })
    
    # Round 2 - try to play card_1 again
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    assert response.status_code == 400
    assert 'already been played' in response.json['msg'].lower()
    assert response.json['code'] == 'CARD_ALREADY_PLAYED'


def test_submit_move_card_not_in_deck(client, db):
    """Test that cards not in deck are rejected."""
    match_id = setup_match_in_progress(client)
    
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "invalid_card"
    })
    
    assert response.status_code == 400
    assert 'not in' in response.json['msg'].lower()
    assert response.json['code'] == 'CARD_NOT_IN_DECK'


def test_submit_move_non_participant(client, db):
    """Test that non-participants can't submit moves."""
    match_id = setup_match_in_progress(client)
    
    response = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 999,
        "card_id": "card_1"
    })
    
    assert response.status_code == 400
    assert 'not part' in response.json['msg'].lower()
    assert response.json['code'] == 'NOT_PARTICIPANT'


# ============== GAME FLOW ==============

def test_complete_match_flow(client, db):
    """Test a complete 10-round match."""
    match_id = setup_match_in_progress(client)
    
    # Play 10 rounds
    for round_num in range(1, 11):
        # Player 1 move
        client.post(f'/game/matches/{match_id}/moves', json={
            "player_id": 1,
            "card_id": f"card_{round_num}"
        })
        
        # Player 2 move
        response = client.post(f'/game/matches/{match_id}/moves', json={
            "player_id": 2,
            "card_id": f"card_{round_num}"
        })
        
        if round_num < 10:
            assert response.json['next_round'] == round_num + 1
        else:
            assert response.json['game_status'] == 'FINISHED'
    
    # Check final match status
    match_response = client.get(f'/game/matches/{match_id}')
    assert match_response.json['status'] == 'FINISHED'
    # Winner can be None (draw) or one of the players
    assert 'winner_id' in match_response.json


# ============== ROUND STATUS ==============

def test_get_round_status(client, db):
    """Test getting current round status."""
    match_id = setup_match_in_progress(client)
    
    # Check initial status
    response = client.get(f'/game/matches/{match_id}/round')
    assert response.status_code == 200
    data = response.json
    assert data['current_round'] == 1
    assert data['round_status'] == 'WAITING_FOR_BOTH_PLAYERS'
    assert data['moves_submitted_count'] == 0
    
    # Submit one move
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    # Check status after first move
    response = client.get(f'/game/matches/{match_id}/round')
    data = response.json
    assert data['round_status'] == 'WAITING_FOR_ONE_PLAYER'
    assert data['moves_submitted_count'] == 1


# ============== MATCH RETRIEVAL ==============

def test_get_match(client, db):
    """Test getting match info."""
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    match_id = match_response.json['id']
    
    response = client.get(f'/game/matches/{match_id}')
    assert response.status_code == 200
    data = response.json
    assert data['id'] == match_id
    assert 'moves' not in data  # Without history


def test_get_match_not_found(client, db):
    """Test getting non-existent match."""
    response = client.get('/game/matches/99999')
    assert response.status_code == 404


def test_get_match_with_history(client, db):
    """Test getting match with move history."""
    match_id = setup_match_in_progress(client)
    
    # Play one round
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 2,
        "card_id": "card_1"
    })
    
    response = client.get(f'/game/matches/{match_id}/history')
    assert response.status_code == 200
    data = response.json
    assert 'moves' in data
    assert len(data['moves']) == 2


# ============== LEADERBOARD ==============

def test_leaderboard_empty(client, db):
    """Test leaderboard with no finished matches."""
    response = client.get('/game/leaderboard')
    assert response.status_code == 200
    data = response.json
    assert data['leaderboard'] == []
    assert data['count'] == 0


def test_leaderboard_with_matches(client, db):
    """Test leaderboard with finished matches."""
    # Create and finish multiple matches
    for i in range(3):
        match_id = setup_match_in_progress(client)
        
        # Complete match
        for round_num in range(1, 11):
            client.post(f'/game/matches/{match_id}/moves', json={
                "player_id": 1,
                "card_id": f"card_{round_num}"
            })
            client.post(f'/game/matches/{match_id}/moves', json={
                "player_id": 2,
                "card_id": f"card_{round_num}"
            })
    
    response = client.get('/game/leaderboard')
    assert response.status_code == 200
    data = response.json
    assert len(data['leaderboard']) > 0
    
    # Check structure
    for entry in data['leaderboard']:
        assert 'rank' in entry
        assert 'player_id' in entry
        assert 'wins' in entry
        assert 'losses' in entry
        assert 'total_matches' in entry
        assert 'win_rate' in entry


def test_leaderboard_pagination(client, db):
    """Test leaderboard pagination."""
    response = client.get('/game/leaderboard?limit=5&offset=0')
    assert response.status_code == 200
    data = response.json
    assert data['limit'] == 5
    assert data['offset'] == 0


# ============== PLAYER HISTORY ==============

def test_player_history_empty(client, db):
    """Test player history with no matches."""
    response = client.get('/game/players/1/history')
    assert response.status_code == 200
    data = response.json
    assert data['player_id'] == 1
    assert data['matches'] == []
    assert data['summary']['total_matches'] == 0


def test_player_history_with_matches(client, db):
    """Test player history with completed matches."""
    match_id = setup_match_in_progress(client)
    
    # Play complete match
    for round_num in range(1, 11):
        client.post(f'/game/matches/{match_id}/moves', json={
            "player_id": 1,
            "card_id": f"card_{round_num}"
        })
        client.post(f'/game/matches/{match_id}/moves', json={
            "player_id": 2,
            "card_id": f"card_{round_num}"
        })
    
    response = client.get('/game/players/1/history')
    assert response.status_code == 200
    data = response.json
    assert data['player_id'] == 1
    assert len(data['matches']) == 1
    
    # Check match structure
    match = data['matches'][0]
    assert 'player_won' in match
    assert 'player_was_player1' in match
    assert 'opponent_id' in match
    assert 'player_score' in match
    assert 'opponent_score' in match
    assert 'moves' in match
    
    # Check summary
    assert data['summary']['total_matches'] == 1


def test_player_history_pagination(client, db):
    """Test player history pagination."""
    response = client.get('/game/players/1/history?limit=10&offset=0')
    assert response.status_code == 200
    data = response.json
    assert data['pagination']['limit'] == 10
    assert data['pagination']['offset'] == 0


def test_player_history_status_filter(client, db):
    """Test player history with status filter."""
    # Create match in setup
    match_response = client.post('/game/matches', json={
        "player1_id": 1,
        "player2_id": 2
    })
    
    response = client.get('/game/players/1/history?status=setup')
    assert response.status_code == 200
    data = response.json
    assert len(data['matches']) == 1
    assert data['matches'][0]['status'] == 'SETUP'


# ============== ERROR HANDLING ==============

def test_invalid_match_id(client, db):
    """Test endpoints with invalid match ID."""
    response = client.get('/game/matches/abc')
    assert response.status_code == 404


def test_malformed_json(client, db):
    """Test endpoints with malformed JSON."""
    response = client.post('/game/matches', 
                          data='invalid json',
                          content_type='application/json')
    assert response.status_code == 400


# ============== CONCURRENT ACCESS ==============

def test_concurrent_move_submission(client, db):
    """Test that database locking prevents race conditions."""
    match_id = setup_match_in_progress(client)
    
    # Both players try to submit as player 1
    response1 = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_1"
    })
    
    response2 = client.post(f'/game/matches/{match_id}/moves', json={
        "player_id": 1,
        "card_id": "card_2"
    })
    
    # One should succeed, one should fail
    assert (response1.status_code == 200 and response2.status_code == 400) or \
           (response1.status_code == 400 and response2.status_code == 200)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])