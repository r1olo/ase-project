import pytest

from auth.app import create_test_app as create_auth_test_app
from auth.extensions import db as auth_db, redis_manager
from catalogue.app import create_test_app as create_catalogue_test_app
from catalogue.extensions import db as catalogue_db


@pytest.fixture
def auth_app():
    app = create_auth_test_app()
    ctx = app.app_context()
    ctx.push()
    yield app
    auth_db.session.remove()
    auth_db.drop_all()
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
    catalogue_db.session.remove()
    catalogue_db.drop_all()
    ctx.pop()


@pytest.fixture
def catalogue_client(catalogue_app):
    return catalogue_app.test_client()
