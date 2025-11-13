"""Flask extension singletons for the auth service."""

from __future__ import annotations

from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager

from common.redis_manager import RedisManager


bcrypt = Bcrypt()
db = SQLAlchemy()
jwt = JWTManager()
redis_manager = RedisManager()
