import io
from datetime import datetime, timedelta

import pytest

from app import db
from app.models import Event, EventRegistration, Post, School, User
from tests.conftest import login, make_user


def _fake_pdf():
    return (io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "doc.pdf")


def _fake_bad_file():
    # Plain text file disguised with .pdf extension - magic bytes will fail!
    return (io.BytesIO(b"Hello world, this is a plain text file not a PDF"), "fake.pdf")


@pytest.fixture
def test_setup(app):
    """Sets up an approved school, a pending school, and users for permission matrix tests."""
    with app.app_context():
        admin = make_user("perm_admin@example.com", role="admin")
        admin.is_verified = True

        user = make_user("perm_user@example.com", role="user")
        user.is_verified = True

        s_owner = make_user("perm_school@example.com", role="school")
        s_owner.is_verified = True

        school = School(
            owner_id=s_owner.id,
            name="St. Paul School",
            name_key="st. paul school",
            udise_code="23260199991",
            board="CBSE",
            address="Ring Road",
            city="Indore",
            state="Madhya Pradesh",
            pincode="452001",
            established_year=1995,
            principal_phone="9826099991",
            official_email="stpaul@example.com",
            status="approved",
            fee_min=25000,
            fee_max=50000,
        )
        db.session.add(school)
        db.session.commit()

        event = Event(
            school_id=school.id,
            title="Intimate Workshop",
            description="Limited seats workshop",
            venue="Room 101",
            starts_at=datetime.now() + timedelta(days=5),
            capacity=1,
        )
        db.session.add(event)
        db.session.commit()

        return {
            "school_id": school.id,
            "event_id": event.id,
        }


def test_anonymous_access_matrix(client, test_setup):
    """Anonymous visitors must be redirected to login for protected pages."""
    school_id = test_setup["school_id"]
    event_id = test_setup["event_id"]

    # Public pages must be 200 OK
    assert client.get("/").status_code == 200
    assert client.get("/schools").status_code == 200
    assert client.get(f"/schools/{school_id}").status_code == 200
    assert client.get("/events").status_code == 200
    assert client.get(f"/events/{event_id}").status_code == 200
    assert client.get("/schools/nearby").status_code == 200

    # Protected routes must redirect to login
    protected = [
        "/dashboard",
        "/feed",
        "/priorities",
        "/matches",
        "/shortlist",
        "/school/profile",
        "/school/connections",
        "/school/inquiries",
        "/admin/schools",
        "/admin/users",
    ]
    for url in protected:
        r = client.get(url)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]


def test_user_role_permissions(client, test_setup):
    """Parent/student users can view user features but get 403 on school/admin routes."""
    login(client, "perm_user@example.com")

    # Allowed user routes
    assert client.get("/dashboard", follow_redirects=True).status_code == 200
    assert client.get("/feed").status_code == 200
    assert client.get("/priorities").status_code == 200
    assert client.get("/shortlist").status_code == 200

    # Forbidden school/admin routes (403)
    assert client.get("/school/profile").status_code == 403
    assert client.get("/school/connections").status_code == 403
    assert client.get("/school/inquiries").status_code == 403
    assert client.get("/admin/schools").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_school_role_permissions(client, test_setup):
    """Approved school owner can view school tools but get 403 on admin or user-only routes."""
    login(client, "perm_school@example.com")

    # Allowed school routes
    assert client.get("/dashboard", follow_redirects=True).status_code == 200
    assert client.get("/school/profile").status_code == 200
    assert client.get("/school/connections").status_code == 200
    assert client.get("/school/inquiries").status_code == 200
    assert client.get("/feed").status_code == 200

    # Forbidden admin routes (403)
    assert client.get("/admin/schools").status_code == 403
    assert client.get("/admin/users").status_code == 403


def test_unverified_school_registration_blocked(client, app):
    """School registration requires email verification first."""
    user = make_user("unverified_principal@example.com", role="school", is_verified=False)

    login(client, "unverified_principal@example.com")
    r = client.get("/school/register", follow_redirects=True)
    assert b"verify your email" in r.data


def test_bad_file_magic_bytes_rejected(client, test_setup):
    """Files with wrong magic bytes are caught and rejected."""
    make_user("new_principal@example.com", role="school", is_verified=True)
    login(client, "new_principal@example.com")

    reg_data = {
        "name": "Fake Document School",
        "udise_code": "23260199992",
        "board": "CBSE",
        "established_year": 2010,
        "address": "Main Road",
        "city": "Indore",
        "state": "Madhya Pradesh",
        "pincode": "452001",
        "principal_phone": "9826099992",
        "official_email": "fake@example.com",
        "doc_affiliation": _fake_bad_file(),
        "doc_recognition": _fake_pdf(),
        "doc_principal_id": _fake_pdf(),
    }
    r = client.post("/school/register", data=reg_data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"content does not match its type" in r.data or b"not a valid" in r.data


def test_event_capacity_limit(client, test_setup):
    """Event spots limit prevents overbooking."""
    event_id = test_setup["event_id"]

    # User 1 registers (fills the 1 spot)
    login(client, "perm_user@example.com")
    r = client.post(f"/events/{event_id}/join", data={"participants": 1}, follow_redirects=True)
    assert b"You have joined this event" in r.data
    client.post("/logout")

    # User 2 tries to register
    make_user("perm_user2@example.com", role="user", is_verified=True)
    login(client, "perm_user2@example.com")

    r = client.post(f"/events/{event_id}/join", data={"participants": 1}, follow_redirects=True)
    assert b"full" in r.data or b"remaining" in r.data


def test_expired_or_tampered_password_token(client, app):
    """Tampered or invalid password reset tokens fail safely."""
    r = client.get("/reset-password/totally-invalid-token", follow_redirects=True)
    assert b"invalid or has expired" in r.data
