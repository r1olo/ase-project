# tests/test_game_engine_api.py
import pytest
import requests # We will mock this module

# This is the mock data we will return from the 'catalogue' service
MOCK_DECK_STATS = {
    "abruzzo": {"economy": 5, "food": 5, "environment": 6, "special": 7, "total": 5.8},
    "lazio": {"economy": 8, "food": 8, "environment": 6, "special": 10, "total": 8.0},
    "sicilia": {"economy": 2, "food": 9, "environment": 10, "special": 10, "total": 7.8},
    "veneto": {"economy": 8, "food": 7, "environment": 8, "special": 6, "total": 7.3},
    # ... add more if your game logic requires more rounds
}

# This class mocks the 'requests.post' response
class MockCatalogueResponse:
    def raise_for_status(self):
        pass
    
    def json(self):
        # Return the full stats map for the requested cards
        # In a real test, you might check the input JSON
        # but for this, we just return the full map.
        return MOCK_DECK_STATS

def test_full_game_flow(game_engine_client, monkeypatch):
    """
    Tests the entire API flow from match creation to game end.
    """
    
    # --- 1. Mock the Catalogue Service ---
    # We patch 'requests.post' which is used in the 'choose_deck' route.
    # (Even though it's commented out in your file, this is how you *should* test it)
    
    # If you are NOT using the real 'requests.post' yet and are
    # relying on the 'MOCK DATA' block inside 'choose_deck',
    # you can skip this monkeypatch section.
    
    def mock_post(url, json):
        # You could add assertions here:
        # assert url == "http://catalogue-service.url/cards/batch-lookup"
        # assert "card_ids" in json
        return MockCatalogueResponse()

    # This replaces 'requests.post' with our 'mock_post' function
    # inside the 'game_engine.routes' file.
    monkeypatch.setattr("game_engine.routes.requests.post", mock_post)

    # --- 2. Create Match ---
    resp = game_engine_client.post("/game/matches", json={
        "player1_id": 100,
        "player2_id": 200
    })
    assert resp.status_code == 201
    match_data = resp.get_json()
    match_id = match_data["id"]
    assert match_data["status"] == "SETUP"

    # --- 3. Player 1 Submits Deck ---
    p1_deck_ids = ["abruzzo", "lazio"] # Simple 2-card deck
    resp = game_engine_client.post(f"/game/matches/{match_id}/deck", json={
        "player_id": 100,
        "deck": p1_deck_ids
    })
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "SETUP" # Still waiting for P2

    # --- 4. Player 2 Submits Deck ---
    p2_deck_ids = ["sicilia", "veneto"]
    resp = game_engine_client.post(f"/game/matches/{match_id}/deck", json={
        "player_id": 200,
        "deck": p2_deck_ids
    })
    assert resp.status_code == 200
    match_data = resp.get_json()
    assert match_data["status"] == "IN_PROGRESS" # Game starts!
    
    # --- 5. Play Round 1 ---
    # Get the category for the round
    resp = game_engine_client.get(f"/game/matches/{match_id}/round")
    assert resp.status_code == 200
    category = resp.get_json()["current_round_category"]
    
    # Player 1 plays 'lazio'
    resp_p1 = game_engine_client.post(f"/game/matches/{match_id}/moves", json={
        "player_id": 100,
        "card_id": "lazio"
    })
    assert resp_p1.status_code == 200
    assert resp_p1.get_json()["status"] == "WAITING_FOR_OPPONENT"
    
    # Player 2 plays 'sicilia'
    resp_p2 = game_engine_client.post(f"/game/matches/{match_id}/moves", json={
        "player_id": 200,
        "card_id": "sicilia"
    })
    assert resp_p2.status_code == 200
    round_result = resp_p2.get_json()
    assert round_result["status"] == "ROUND_PROCESSED"
    
    # --- 6. (Game Logic) ... ---
    # We'll assume the game ends after 2 rounds (one for each card)
    
    # --- 7. Play Round 2 ---
    resp = game_engine_client.get(f"/game/matches/{match_id}/round")
    category_r2 = resp.get_json()["current_round_category"]
    
    # Player 1 plays 'abruzzo'
    game_engine_client.post(f"/game/matches/{match_id}/moves", json={
        "player_id": 100,
        "card_id": "abruzzo"
    })
    
    # Player 2 plays 'veneto'
    resp_r2_final = game_engine_client.post(f"/game/matches/{match_id}/moves", json={
        "player_id": 200,
        "card_id": "veneto"
    })
    
    final_result = resp_r2_final.get_json()
    assert final_result["game_status"] == "FINISHED"
    assert final_result["winner_id"] is not None
    
    # --- 8. Check History ---
    resp_hist = game_engine_client.get(f"/game/matches/{match_id}/history")
    assert resp_hist.status_code == 200
    history = resp_hist.get_json()
    assert len(history["moves"]) == 4 # 2 players, 2 rounds