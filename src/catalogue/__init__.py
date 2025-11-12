from .catalogue import catalogue
from flask import Flask
from config import Config, TestConfig
from extensions import db

# implementation of factory function
def _create_app(testing=False):
    app = Flask(__name__)

    # use a particular config based on whether we're testing
    conf = TestConfig() if testing else Config()
    app.config.from_object(conf)

    # init database and populate tables if they don't exist
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # register routes
    app.register_blueprint(catalogue)

    return app

# create normal app
def create_app():
    return _create_app(testing=False)

# create test app
def create_test_app():
    return _create_app(testing=True)
