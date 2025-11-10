from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from .routes import main

# app is created here
def create_app_with_db():
    app = Flask(__name__)

    # load config? TODO (also look into from_prefixed_env)
    app.config.from_object("app.config.Config")

    # init database
    db = SQLAlchemy()
    db.init_app(app)

    # register routes
    app.register_blueprint(main)

    return (app, db)
