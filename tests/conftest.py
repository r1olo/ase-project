# common pytest fixtures (should make an app per microservice)
import pytest

from auth.app import create_test_app as create_auth_test_app

# extensions are shared (common/extensions.py)
from common.extensions import db, redis_manager

from catalogue.app import create_test_app as create_catalogue_test_app
from matchmaking.app import create_test_app as create_matchmaking_test_app
# from game_engine.app import create_test_app as create_game_engine_test_app

@pytest.fixture
def auth_app():
    app = create_auth_test_app()
    ctx = app.app_context()
    ctx.push()
    yield app
    db.session.remove()
    db.drop_all()
    redis_manager.conn.flushall()
    ctx.pop()

@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()

@pytest.fixture
def catalogue_app():
    app = create_catalogue_test_app()
    ctx = app.app_context()
    ctx.push()
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()

@pytest.fixture
def catalogue_client(catalogue_app):
    return catalogue_app.test_client()

@pytest.fixture
def matchmaking_app():
    app = create_matchmaking_test_app()
    ctx = app.app_context()
    ctx.push()
    yield app
    redis_manager.conn.flushall()
    ctx.pop()

@pytest.fixture
def matchmaking_client(matchmaking_app):
    return matchmaking_app.test_client()

@pytest.fixture
def game_engine_app():
    app = create_game_engine_test_app()
    ctx = app.app_context()
    ctx.push()
    yield app
    db.session.remove()
    db.drop_all()
    ctx.pop()

@pytest.fixture
def game_engine_client(game_engine_app):
    return game_engine_app.test_client()
