# common test utilities (fixups to create environmnt)
from app import create_test_app
from app.extensions import db
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
