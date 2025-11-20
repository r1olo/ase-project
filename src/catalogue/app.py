"""Application factory for the Card Catalogue microservice."""
from __future__ import annotations
from .config import Config, TestConfig
from .models import Card
from .routes import catalogue as catalogue_blueprint
from common.app_factory import create_flask_app
from common.extensions import db
from flask import Flask

import json

# fill the database at init
def _init_cards_db():
    with open("cards/cards.json") as file:
        cards_data = json.load(file)
        for _, card_info in cards_data.items():
            card = Card.query.filter_by(name=card_info["name"]).first()
            if card is not None:
                continue
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

# generic create app interface for cards
def _create_app(config) -> Flask:
    return create_flask_app(
        name=__name__,
        config_obj=config,
        extensions=(db,),
        blueprints=(catalogue_blueprint,),
        init_app_context_steps=(_init_cards_db,)
    )

def create_app() -> Flask:
    return _create_app(Config())

def create_test_app() -> Flask:
    return _create_app(TestConfig())

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
