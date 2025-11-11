from app.models.card import Card
from app.extensions import db
import json

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

    # fetch all cards
    resp = client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["data"]) == 2

def test_get_single_card_success(client):
    # add a card to the database
    card = Card("Molise", "/images/11-molise.png", 4, 2, 3, 8, 17.0)
    db.session.add(card)
    db.session.commit()

    # fetch the card by id
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
    