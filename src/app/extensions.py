# global Flask extensions
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

# bcrypt extension
bcrypt = Bcrypt()

# SQLAlchemy extension
db = SQLAlchemy()

# JWTManager extension
jwt = JWTManager()
