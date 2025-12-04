"""Application factory for the Card Catalogue microservice."""
from __future__ import annotations
from .config import Config, TestConfig
from .mock_routes import mock_catalogue as catalogue_blueprint
from common.app_factory import create_flask_app
from flask import Flask, current_app

import json 

# fill the database at init
def _init_mock_cards_db():
    current_app.cards_db = {}
    with open("cards/cards.json") as file:
        cards = json.load(file)
        for idx, card in enumerate(cards):
            card["id"] = idx + 1
        current_app.cards_db = cards

def _create_app(config) -> Flask:
    return create_flask_app(
        name=__name__,
        config_obj=config,
        blueprints=(catalogue_blueprint,),
        init_app_context_steps=(_init_mock_cards_db,)
    )

def create_app() -> Flask:
    return _create_app(Config())

def create_test_app() -> Flask:
    return _create_app(TestConfig())

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000)
