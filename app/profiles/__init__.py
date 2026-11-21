
from flask import Blueprint

bp = Blueprint("profiles", __name__)

from app.profiles import routes  # noqa: E402, F401