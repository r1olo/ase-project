from app.models.card import Card
from app.extensions import db

def test_get_all_cards_empty_db(client):
    # ensure no cards in the database
    resp = client.get("/cards")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["data"] == []

def test_get_all_cards_with_data(client):
    # add some cards to the database
    card1 = Card("Campania", "/images/04-campania.png", 3, 9, 9, 10, 31.0)
    card2 = Card("Lazio", "/images/07-lazio.png", 8, 8, 6, 10, 32.0)
    card3 = Card("Liguria", "/images/08-liguria.png", 7, 7, 6, 10, 30.0)
    card4 = Card("Sicilia", "/images/15-sicilia.png", 2, 9, 10, 10, 31.0)
    db.session.add(card1)
    db.session.add(card2)
    db.session.add(card3)
    db.session.add(card4)
    db.session.commit()

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
    assert data["economy"] == 20

def test_get_single_card_not_found(client):
    # try to fetch a non-existent card
    resp = client.get("/cards/9999")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data["msg"] == "Card not found"