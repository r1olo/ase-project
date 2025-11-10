from flask import Flask
from .auth import auth
from .config import Config
from .extensions import bcrypt, db, jwt
from .routes import main

# app is created here
def create_app(config_override=None):
    app = Flask(__name__)

    # load config? TODO (also look into from_prefixed_env)
    Config.init_keys()
    app.config.from_object(Config)

    # expect a possible override for unit tests
    if config_override:
        app.config.update(config_override)

    # init database and populate tables if they don't exist
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # init bcrypt
    bcrypt.init_app(app)

    # init jwtmanager
    jwt.init_app(app)

    # register routes
    app.register_blueprint(main)
    app.register_blueprint(auth, url_prefix="/auth")

    return app
