# generic app factory
from flask import Flask

# create a Flask application with the following parameters:
#   config_obj: A class instance containing configuration parameters
#   extensions: A list of extension objects to init with this app
#   blueprints: A list of Flask blueprints to register within the app
#   init_app_context_steps: A list of things to do with this app's context
def create_flask_app(*, config_obj, extensions, blueprints,
                     init_app_context_steps):
    # create app and configure it
    app = Flask(__name__)
    app.config.from_object(config_obj)

    # init all the extensions
    for ext in extensions:
        ext.init_app(app)

    # perform initialization steps in app's context
    with app.app_context():
        for step in init_app_context_steps:
            step(app)

    # register blueprints
    for bp in blueprints:
        app.register_blueprint(bp)

    # return app
    return app
