from flask import Flask
from .routes import main

# app is created here
def create_app():
    app = Flask(__name__)

    # load config? TODO
    # load DB? TODO

    app.register_blueprint(main)

    return app
