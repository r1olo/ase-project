from catalogue import create_test_app
from catalogue.models.card import Card
from extensions import db
import json
import pytest

@pytest.fixture
def app():
    app = create_test_app()
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def runner(app):
    return app.test_cli_runner()

### helper functions

# fill the database with cards from the json file
def fill_db():
    with open("cards/cards.json") as file:
        cards_data = json.load(file)
        for _, card_info in cards_data.items():
            card = Card(
                name=card_info["name"],
                image=card_info["image"],
                economy=card_info["economy"],
                food=card_info["food"],
                environment=card_info["environment"],
                special=card_info["special"],
                total=card_info["total"],
            )
            db.session.add(card)
    db.session.commit()

### test cases for catalogue cards endpoints

def test_get_all_cards_empty_db(client):
    # ensure no cards in the database
    resp = client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == []

def test_get_all_cards(client):
    # add cards to the database
    fill_db()

    # try to fetch all cards
    resp = client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    with open("cards/cards.json") as file:
        cards_data = json.load(file)
        assert len(data["data"]) == len(cards_data)
        for card in data["data"]:
            card.pop("id")  # remove id for comparison
            assert card in cards_data.values()
 
def test_get_single_card_success(client):
    # add a card to the database
    card = Card("Molise", "/images/11-molise.png", 4, 2, 3, 8, 17.0)
    db.session.add(card)
    db.session.commit()

    # try to fetch the card by id
    resp = client.get(f"/cards/{card.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "Molise"

def test_get_single_card_not_found(client):
    # try to fetch a non-existent card
    resp = client.get("/cards/123456789")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["msg"] == "Card not found"

def test_get_single_card_invalid_id(client):
    # try to fetch a card using an invalid ID
    resp = client.get("/cards/abc123")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["msg"] == "Invalid card ID"
    