from catalogue.models import Card
from common.extensions import db

import json

# fill the database with cards from the json file
def _fill_db():
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
def test_get_all_cards_empty_db(catalogue_client):
    # ensure no cards in the database
    resp = catalogue_client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == []

def test_get_all_cards(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    # try to fetch all cards
    resp = catalogue_client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data is not None
    with open("cards/cards.json") as file:
        cards = json.load(file)
        assert len(data["data"]) == len(cards)
        for card_data in data["data"]:
            card_data.pop("id")  # remove id for comparison
            assert card_data in cards.values()
 
def test_get_single_card_success(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    # try to fetch the card by id
    resp = catalogue_client.get(f"/cards/8")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "Liguria"

def test_get_single_card_not_found(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    # try to fetch a non-existent card
    resp = catalogue_client.get("/cards/123456789")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["msg"] == "Card not found"

def test_get_single_card_invalid_id(disable_jwt, catalogue_client):
    disable_jwt()

    # try to fetch a card using an invalid ID
    resp = catalogue_client.get("/cards/abc123")
    assert resp.status_code == 404

def test_cards_validation_empty_body(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    # try to validate an empty payload
    resp = catalogue_client.get("/cards/validation", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == True

def test_cards_validation_success(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    data = [
        Card.query.filter_by(name="Campania").first(),
        Card.query.filter_by(name="Lazio").first(),
        Card.query.filter_by(name="Liguria").first(),
        Card.query.filter_by(name="Sicilia").first(),
        Card.query.filter_by(name="Molise").first(),
        Card.query.filter_by(name="Veneto").first(),
        Card.query.filter_by(name="Trentino-Alto Adige").first()
    ]
    
    resp = catalogue_client.get("/cards/validation", json={"data": [card.to_dict(relative=True) for card in data]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == True

def test_cards_validation_failure(disable_jwt, catalogue_client):
    disable_jwt()
    _fill_db()

    with open("cards/cards.json") as file:
        cards = json.load(file)
        # define the request payload from json file with no id field
        data = [
            cards.get("campania"),
            cards.get("lazio"),
            cards.get("liguria"),
            cards.get("sicilia"),
            cards.get("molise"),
            cards.get("veneto"),
            cards.get("trentino_alto_adige"),
        ]
        
        resp = catalogue_client.get("/cards/validation", json={"data": data})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == False
