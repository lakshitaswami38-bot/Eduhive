from flask import Blueprint

bp = Blueprint("matches", __name__)

from app.matches import routes  # noqa: E402, F401