import json

from catalogue.models import Card
from catalogue.extensions import db


def fill_db():
    with open("cards/cards.json") as file:
        cards_data = json.load(file)
        for card_info in cards_data.values():
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


def test_get_all_cards_empty_db(catalogue_client):
    resp = catalogue_client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == []


def test_get_all_cards(catalogue_client):
    fill_db()
    resp = catalogue_client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    with open("cards/cards.json") as file:
        cards_data = json.load(file)
        assert len(data["data"]) == len(cards_data)
        for card in data["data"]:
            card_copy = dict(card)
            card_copy.pop("id")
            assert card_copy in cards_data.values()


def test_get_single_card_success(catalogue_client):
    card = Card(
        name="Molise",
        image="/images/11-molise.png",
        economy=4,
        food=2,
        environment=3,
        special=8,
        total=17.0,
    )
    db.session.add(card)
    db.session.commit()

    resp = catalogue_client.get(f"/cards/{card.id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["name"] == "Molise"


def test_get_single_card_not_found(catalogue_client):
    resp = catalogue_client.get("/cards/123456789")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["msg"] == "Card not found"


def test_get_single_card_invalid_id(catalogue_client):
    resp = catalogue_client.get("/cards/abc123")
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["msg"] == "Invalid card ID"
