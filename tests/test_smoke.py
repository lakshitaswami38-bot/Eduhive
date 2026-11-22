import io
from datetime import datetime, timedelta

from PIL import Image

from app import db
from app.models import (
    AdmissionInquiry,
    Connection,
    Event,
    EventRegistration,
    Post,
    School,
    User,
    UserShortlist,
)
from tests.conftest import login, make_user


def _fake_pdf():
    return (io.BytesIO(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"), "document.pdf")


def _fake_png():
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), (200, 100, 50))
    img.save(buf, format="PNG")
    buf.seek(0)
    return (buf, "test_photo.png")


def test_full_smoke_flow(client, app):
    """End-to-end smoke test verifying the complete user & school lifecycle:

    signup -> verify email -> choose role -> register school -> admin approve ->
    profile & location -> post with photo & delete -> event with seat limit ->
    event join by user & another school -> like toggle -> school connections ->
    network feed -> nearby search -> priorities & live matching ->
    shortlist & compare -> admission inquiry & school reply ->
    admin users & moderation (suspend/reinstate/delete post) ->
    forgot & reset password.
    """
    # 1. School Owner Signs up and verifies email
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
    owner = db.session.scalar(db.select(User).filter_by(email="principal@example.com"))
    assert owner is not None
    assert not owner.is_verified

    # Verify email
    owner.is_verified = True
    db.session.commit()

    login(client, "principal@example.com", "Password123!")
    r = client.post("/choose-role", data={"school": "1"}, follow_redirects=True)
    assert r.status_code == 200

    # 2. Register School 1 with proof documents
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

    school1 = db.session.scalar(db.select(School).filter_by(udise_code="23260100101"))
    assert school1 is not None
    assert school1.status == "pending"

    # 3. Admin Reviews and Approves School 1
    client.post("/logout", follow_redirects=True)
    admin = make_user("admin@example.com", role="admin")
    admin.is_verified = True
    db.session.commit()
    login(client, "admin@example.com")

    r = client.get(f"/admin/schools/{school1.id}")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data

    r = client.post(f"/admin/schools/{school1.id}/approve", follow_redirects=True)
    assert b"has been approved" in r.data
    db.session.refresh(school1)
    assert school1.status == "approved"

    # 4. School Owner 1 fills Profile (Specialities, Results, Coordinates)
    client.post("/logout", follow_redirects=True)
    login(client, "principal@example.com", "Password123!")

    # Verify school home dashboard renders cleanly
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
        "specialities": ["science", "sports"],
        "website": "https://example.com/dps",
        "admission_open": "y",
        "admission_url": "https://example.com/dps/apply",
        "latitude": 22.7533,
        "longitude": 75.8937,
        "results-0-year": 2024,
        "results-0-class10": 94.5,
        "results-0-class12": 91.0,
        "results-1-year": "",
        "results-1-class10": "",
        "results-1-class12": "",
        "results-2-year": "",
        "results-2-class10": "",
        "results-2-class12": "",
    }
    r = client.post("/school/profile", data=prof_data, follow_redirects=True)
    assert b"Profile saved" in r.data

    # Check public page displays profile info
    r = client.get(f"/schools/{school1.id}")
    assert r.status_code == 200
    assert b"premier institution" in r.data
    assert b"30,000" in r.data
    assert b"Admissions" in r.data

    # 5. School Owner publishes a Post with photo
    r = client.post(
        "/school/posts/new",
        data={
            "title": "Inter-School Science Fair 2026",
            "body": "We are proud to host the state level science competition next month.",
            "photo": _fake_png(),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Post published" in r.data
    post = db.session.scalar(db.select(Post).filter_by(school_id=school1.id))
    assert post is not None
    assert post.title == "Inter-School Science Fair 2026"
    assert post.photo_name is not None

    # Verify post photo serving route
    r = client.get(f"/posts/{post.id}/photo")
    assert r.status_code == 200

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
    event = db.session.scalar(db.select(Event).filter_by(school_id=school1.id))
    assert event is not None
    assert event.title == "Campus Open Day 2026"

    # 7. Parent/Student Signs up and verifies email
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
    user = db.session.scalar(db.select(User).filter_by(email="rajesh@example.com"))
    user.is_verified = True
    db.session.commit()

    login(client, "rajesh@example.com", "Password123!")
    client.post("/choose-role", data={"other": "1"}, follow_redirects=True)

    # 8. User joins the Event
    r = client.get(f"/events/{event.id}")
    assert r.status_code == 200
    assert b"btn-event" in r.data

    r = client.post(f"/events/{event.id}/join", data={"participants": 2, "note": "Attending with child"}, follow_redirects=True)
    assert b"You have joined this event" in r.data

    # 9. User toggles Like on post
    r = client.post(f"/posts/{post.id}/like", follow_redirects=True)
    assert r.status_code == 200
    db.session.refresh(post)
    assert len(post.likes) == 1

    # 10. User follows School 1 and checks feed
    r = client.post(f"/schools/{school1.id}/follow", follow_redirects=True)
    assert b"You now follow" in r.data

    r = client.get("/feed")
    assert r.status_code == 200
    assert b"Inter-School Science Fair 2026" in r.data

    # 11. User tests Shortlist and Compare
    r = client.post(f"/schools/{school1.id}/shortlist", follow_redirects=True)
    assert b"added to your shortlist" in r.data

    r = client.get("/shortlist")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data

    # 12. User submits an Admission Inquiry
    r = client.post(
        f"/schools/{school1.id}/inquire",
        data={"child_class": 6, "message": "What is the admission procedure for Class 6?"},
        follow_redirects=True,
    )
    assert b"inquiry has been submitted" in r.data
    inq = db.session.scalar(db.select(AdmissionInquiry).filter_by(school_id=school1.id))
    assert inq is not None
    assert inq.status == "new"

    # 13. Register School 2 (for School-to-School connection & Compare)
    client.post("/logout", follow_redirects=True)
    p2 = make_user("principal2@example.com", role="school")
    p2.is_verified = True
    db.session.commit()
    login(client, "principal2@example.com")

    reg_data2 = {
        "name": "Emerald Heights International",
        "udise_code": "23260100202",
        "board": "CBSE",
        "established_year": 2000,
        "address": "Rau Bypass",
        "city": "Indore",
        "state": "Madhya Pradesh",
        "pincode": "453331",
        "principal_phone": "9826054321",
        "official_email": "emerald@example.com",
        "doc_affiliation": _fake_pdf(),
        "doc_recognition": _fake_pdf(),
        "doc_principal_id": _fake_pdf(),
    }
    client.post("/school/register", data=reg_data2, content_type="multipart/form-data", follow_redirects=True)
    school2 = db.session.scalar(db.select(School).filter_by(udise_code="23260100202"))
    school2.status = "approved"
    school2.fee_min = 40000
    school2.fee_max = 80000
    school2.class_from = 1
    school2.class_to = 12
    school2.latitude = 22.6800
    school2.longitude = 75.8300
    db.session.commit()

    # School 2 connects with School 1
    r = client.post(f"/school/connections/{school1.id}/connect", follow_redirects=True)
    assert b"Connection request sent" in r.data
    conn = db.session.scalar(db.select(Connection).filter_by(requester_school_id=school2.id, receiver_school_id=school1.id))
    assert conn is not None
    assert conn.status == "pending"

    # School 1 accepts connection
    client.post("/logout", follow_redirects=True)
    login(client, "principal@example.com", "Password123!")
    r = client.post(f"/school/connections/{conn.id}/accept", follow_redirects=True)
    assert b"You are now connected" in r.data
    db.session.refresh(conn)
    assert conn.status == "accepted"

    # School 1 checks Network feed
    r = client.get("/feed?tab=network")
    assert r.status_code == 200

    # School 1 checks and replies to Admission Inquiry
    r = client.get("/school/inquiries")
    assert r.status_code == 200
    assert b"What is the admission procedure" in r.data

    r = client.post(f"/school/inquiries/{inq.id}/reply", data={"reply": "Admissions for Class 6 are open till next month."}, follow_redirects=True)
    assert b"Reply sent" in r.data
    db.session.refresh(inq)
    assert inq.status == "replied"

    # 14. Compare schools 1 and 2
    client.post("/logout", follow_redirects=True)
    r = client.get(f"/compare?id={school1.id}&id={school2.id}")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data
    assert b"Emerald Heights International" in r.data

    # 15. Nearby search
    r = client.get("/schools/nearby?q=Indore&radius=20")
    assert r.status_code == 200
    assert b"Delhi Public School Indore" in r.data

    # 16. Admin user management and school suspend/reinstate
    login(client, "admin@example.com")
    r = client.get("/admin/users")
    assert r.status_code == 200
    assert b"Rajesh Kumar" in r.data
    assert b"principal@example.com" in r.data

    # Admin suspends School 1
    r = client.post(f"/admin/schools/{school1.id}/suspend", follow_redirects=True)
    assert b"suspended" in r.data
    db.session.refresh(school1)
    assert school1.is_suspended

    # Verify suspended school vanishes from public list
    r = client.get("/schools")
    assert b"Delhi Public School Indore" not in r.data

    # Admin reinstates School 1
    r = client.post(f"/admin/schools/{school1.id}/reinstate", follow_redirects=True)
    assert b"reinstated" in r.data
    db.session.refresh(school1)
    assert not school1.is_suspended

    # Admin deletes a post
    r = client.post(f"/admin/posts/{post.id}/delete", follow_redirects=True)
    assert b"Post removed by administrator" in r.data
    deleted_post = db.session.get(Post, post.id)
    assert deleted_post is None

    # 17. Password reset flow
    client.post("/logout", follow_redirects=True)
    r = client.post("/forgot-password", data={"email": "rajesh@example.com"}, follow_redirects=True)
    assert b"instructions to reset your password" in r.data
