from flask import Blueprint

bp = Blueprint("follows", __name__)

from app.follows import routes  # noqa: E402, F401