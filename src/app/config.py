# manage config through env vars
import os

# TODO
class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///:memory:")
    JWT_ALGORITHM = "RS256"
    JWT_PRIVATE_KEY = None
    JWT_PUBLIC_KEY = None
    JWT_SECRET_KEY = None

    @classmethod
    def init_keys(cls):
        priv_path = os.getenv("PRIVATE_KEY")
        pub_path = os.getenv("PUBLIC_KEY")

        # if paths are set and valid, read the files
        if priv_path and pub_path and os.path.exists(priv_path) and os.path.exists(pub_path):
            with open(priv_path, "r") as f:
                cls.JWT_PRIVATE_KEY = f.read()
            with open(pub_path, "r") as f:
                cls.JWT_PUBLIC_KEY = f.read()
            cls.JWT_ALGORITHM = "RS256"
            return

        # try default files
        if os.path.exists("jwtRS256.key") and os.path.exists("jwtRS256.key.pub"):
            with open("jwtRS256.key") as f:
                cls.JWT_PRIVATE_KEY = f.read()
            with open("jwtRS256.key.pub") as f:
                cls.JWT_PUBLIC_KEY = f.read()
            cls.JWT_ALGORITHM = "RS256"
            return

        # fallback to symmetric encryption
        cls.JWT_ALGORITHM = "HS256"
        cls.JWT_SECRET_KEY = os.getenv("SECRET_KEY", "supersecretkey")
