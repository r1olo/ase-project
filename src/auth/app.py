# app factory for the auth module
from .config import Config, TestConfig
from common.app_factory import create_flask_app
from common.extensions import bcrypt, db, jwt, redis_manager
from .routes import bp as auth_blueprint

# flask app creation generic function
def _create_app(config_object):
    return create_flask_app(
        name=__name__,
        config_obj=config_object,
        extensions=(db, bcrypt, jwt, redis_manager),
        blueprints=(auth_blueprint,),
        init_app_context_steps=(lambda _: db.create_all(),),
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
    app.run(host="0.0.0.0", port=5000)
