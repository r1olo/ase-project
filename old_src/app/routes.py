# main route entrypoint
from flask import Blueprint

main = Blueprint("main", __name__)

@main.route("/")
def home():
    return "Hello from root"
