from flask import Flask
from flask_jwt_extended import JWTManager, create_access_token

import os

SECRETS_DIR = "secrets"
SECRET_FILE = "jwt_secret"
FILE_PATH = os.path.join(SECRETS_DIR, SECRET_FILE)

app = Flask(__name__)

# this must match the key in the actual application config
app.config["JWT_SECRET_KEY"] = "test-secret" 

jwt = JWTManager(app)

with app.app_context():
    # create a token that never expires used for testing
    token = create_access_token(identity="test_user", expires_delta=False)
    print(token)
    print("\n")

    # write the generated token in a file
    if not os.path.exists(SECRETS_DIR):
        os.makedirs(SECRETS_DIR)
    with open(FILE_PATH, "w") as f:
        f.write(token)
