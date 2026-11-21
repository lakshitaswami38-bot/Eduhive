import os

from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)

login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "info"


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Add it to your .env file.")

    if os.getenv("APP_ENV") == "production":
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    from app import models  # noqa: F401

    from app.cli import register_cli
    register_cli(app)

    from app.auth import bp as auth_bp
    from app.main import bp as main_bp
    from app.schools import bp as schools_bp
    from app.admin import bp as admin_bp
    from app.content import bp as content_bp
    from app.matches import bp as matches_bp
    from app.follows import bp as follows_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(schools_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(content_bp)
    app.register_blueprint(matches_bp)
    app.register_blueprint(follows_bp)

    messages = {
        403: "You do not have permission to open this page.",
        404: "We could not find that page.",
        413: "The files you uploaded are too large.",
        429: "Too many attempts. Please wait a minute and try again.",
        500: "Something went wrong on our side. Please try again.",
    }

    def show_error(error):
        code = getattr(error, "code", 500)
        if code == 500:
            db.session.rollback()
        return render_template(
            "errors/error.html", code=code, message=messages.get(code, "Something went wrong.")
        ), code

    for code in messages:
        app.register_error_handler(code, show_error)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.route("/")
    def home():
        return render_template("home.html")

    return app