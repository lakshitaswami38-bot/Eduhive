import io
from datetime import datetime, timedelta

from app import db
from app.models import Event, Post, School
from tests.conftest import login, make_user


def _fake_pdf():
    return (io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "document.pdf")


def test_full_smoke_flow(client, app):
    """End-to-end smoke test verifying the complete user & school lifecycle:

    register -> approve -> profile -> post -> event -> join -> follow ->
    feed -> priorities -> matches -> dashboards.
    """
    # 1. School Owner Signs up and chooses school role
    r = client.post(
        "/signup",
        data={
            "name": "Principal Sharma",
            "email": "principal@example.com",
            "password": "Password123!",
            "confirm": "Password123!",
        },
        follow_redirects=True,
    )
    assert b"Account created" in r.data

    login(client, "principal@example.com", "Password123!")
    r = client.post("/choose-role", data={"school": "1"}, follow_redirects=True)
    assert r.status_code == 200

    # 2. Register School with proof documents
    reg_data = {
        "name": "Delhi Public School Indore",
        "udise_code": "23260100101",
        "board": "CBSE",
        "established_year": 2005,
        "address": "Bypass Road, Nipania",
        "city": "Indore",
        "state": "Madhya Pradesh",
        "pincode": "452010",
        "principal_phone": "9826012345",
        "official_email": "dps@example.com",
        "doc_affiliation": _fake_pdf(),
        "doc_recognition": _fake_pdf(),
        "doc_principal_id": _fake_pdf(),
    }
    r = client.post("/school/register", data=reg_data, content_type="multipart/form-data", follow_redirects=True)
    assert b"Application submitted" in r.data

    school = db.session.scalar(db.select(School).filter_by(udise_code="23260100101"))
    assert school is not None
    assert school.status == "pending"

    # 3. Admin Reviews and Approves School
    client.post("/logout", follow_redirects=True)
    admin = make_user("admin@example.com", role="admin")
    login(client, "admin@example.com")

    r = client.get(f"/admin/schools/{school.id}")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data

    r = client.post(f"/admin/schools/{school.id}/approve", follow_redirects=True)
    assert b"has been approved" in r.data
    db.session.refresh(school)
    assert school.status == "approved"

    # 4. School Owner fills Profile
    client.post("/logout", follow_redirects=True)
    login(client, "principal@example.com", "Password123!")

    # Verify school home dashboard renders cleanly (no 500 BuildError!)
    r = client.get("/dashboard/school")
    assert r.status_code == 200
    assert b"Welcome, Delhi Public School Indore" in r.data

    prof_data = {
        "about": "Delhi Public School Indore is a premier institution known for excellence in education and sports.",
        "medium": "English",
        "fee_min": 30000,
        "fee_max": 60000,
        "class_from": 1,
        "class_to": 12,
        "student_count": 2500,
        "teacher_count": 120,
        "facilities": ["library", "sports"],
        "website": "https://example.com/dps",
    }
    r = client.post("/school/profile", data=prof_data, follow_redirects=True)
    assert b"Profile saved" in r.data

    # Check public page displays profile info
    r = client.get(f"/schools/{school.id}")
    assert r.status_code == 200
    assert b"premier institution" in r.data
    assert b"30,000" in r.data

    # 5. School Owner publishes a Post
    r = client.post(
        "/school/posts/new",
        data={
            "title": "Inter-School Science Fair 2026",
            "body": "We are proud to host the state level science competition next month.",
        },
        follow_redirects=True,
    )
    assert b"Post published" in r.data
    post = db.session.scalar(db.select(Post).filter_by(school_id=school.id))
    assert post is not None
    assert post.title == "Inter-School Science Fair 2026"

    # 6. School Owner publishes an Event
    event_time = datetime.now() + timedelta(days=10)
    r = client.post(
        "/school/events/new",
        data={
            "title": "Campus Open Day 2026",
            "description": "Parents and students are invited to explore our labs, grounds and interact with teachers.",
            "venue": "Auditorium Hall",
            "starts_at": event_time.strftime("%Y-%m-%dT%H:%M"),
            "capacity": 100,
        },
        follow_redirects=True,
    )
    assert b"Event published" in r.data
    event = db.session.scalar(db.select(Event).filter_by(school_id=school.id))
    assert event is not None
    assert event.title == "Campus Open Day 2026"

    # 7. Parent/Student Signs up and chooses user role
    client.post("/logout", follow_redirects=True)
    client.post(
        "/signup",
        data={
            "name": "Rajesh Kumar",
            "email": "rajesh@example.com",
            "password": "Password123!",
            "confirm": "Password123!",
        },
        follow_redirects=True,
    )
    login(client, "rajesh@example.com", "Password123!")
    client.post("/choose-role", data={"other": "1"}, follow_redirects=True)

    # 8. User joins the Event
    r = client.get(f"/events/{event.id}")
    assert r.status_code == 200
    assert b"btn-event" in r.data  # Verify event button styling is used

    r = client.post(f"/events/{event.id}/join", follow_redirects=True)
    assert b"You have joined this event" in r.data

    # 9. User follows the School
    r = client.post(f"/schools/{school.id}/follow", follow_redirects=True)
    assert b"You now follow" in r.data

    # 10. User checks Feed
    r = client.get("/feed")
    assert r.status_code == 200
    assert b"Inter-School Science Fair 2026" in r.data

    # 11. User sets Priorities
    r = client.post(
        "/priorities",
        data={
            "max_fee": 50000,
            "board": "CBSE",
            "city": "Indore",
            "class_needed": 6,
            "facilities": ["library", "sports"],
            "w_fee": 5,
            "w_board": 3,
            "w_city": 3,
            "w_facilities": 4,
        },
        follow_redirects=True,
    )
    assert b"Priorities saved" in r.data

    # 12. User views Matches (Rule-based weighted ranking)
    r = client.get("/matches")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data
    assert b"fits your budget" in r.data or b"Board: CBSE" in r.data

    # 13. Dashboards verification for all 3 roles
    # User dashboard
    r = client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert b"Welcome" in r.data or b"dashboard/other" in r.request.path

    # School owner dashboard
    client.post("/logout", follow_redirects=True)
    login(client, "principal@example.com", "Password123!")
    r = client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert b"Welcome, Delhi Public School Indore" in r.data

    # Admin dashboard
    client.post("/logout", follow_redirects=True)
    login(client, "admin@example.com")
    r = client.get("/dashboard", follow_redirects=True)
    assert r.status_code == 200
    assert b"Admin dashboard" in r.data
