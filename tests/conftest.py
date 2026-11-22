import pytest

from app import create_app, db
from app.models import User
from config import TestConfig


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def make_user(email, role="user", password="password123", is_verified=True):
    user = User(name="Test", email=email, role=role, is_verified=is_verified)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def login(client, email, password="password123"):
    return client.post("/login", data={"email": email, "password": password}, follow_redirects=True)