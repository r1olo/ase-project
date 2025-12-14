# app factory for the matchmaking module
from common.app_factory import create_flask_app
from common.extensions import jwt, redis_manager
from .config import Config, TestConfig
from .routes import bp as matchmaking_blueprint

# flask app creation generic function
def _create_app(config_object):
    return create_flask_app(
        name=__name__,
        config_obj=config_object,
        extensions=(jwt, redis_manager),
        blueprints=(matchmaking_blueprint,),
        init_app_context_steps=(),
    )

# create a normal config app
def create_app():
    return _create_app(Config())

# create a test config app
def create_test_app():
    return _create_app(TestConfig())

# main Flask entrypoint
if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000) # nosec
