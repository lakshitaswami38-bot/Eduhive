from app import db
from app.models import School
from tests.conftest import login, make_user


def make_school(owner, **kw):
    data = dict(
        owner_id=owner.id, name="Test School", name_key="test school", udise_code="12345678901",
        board="CBSE", address="Road 1", city="Indore", state="MP", pincode="452001",
        established_year=2000, principal_phone="9876543210", official_email="s@x.com",
        status="approved", fee_min=20000, fee_max=40000, class_from=1, class_to=12,
        facilities="library,sports",
    )
    data.update(kw)
    school = School(**data)
    db.session.add(school)
    db.session.commit()
    return school


def test_dashboard_needs_login(client):
    r = client.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_signup_and_wrong_password(client):
    r = client.post("/signup", data={
        "name": "A", "email": "a@x.com", "password": "password123", "confirm": "password123",
    }, follow_redirects=True)
    assert b"Account created" in r.data
    r = login(client, "a@x.com", "wrongpass")
    assert b"Invalid email or password" in r.data


def test_signup_cannot_choose_role(client, app):
    from app.models import User
    client.post("/signup", data={
        "name": "A", "email": "b@x.com", "password": "password123", "confirm": "password123",
        "role": "admin",
    })
    user = db.session.scalar(db.select(User).filter_by(email="b@x.com"))
    assert user.role == "unassigned"


def test_user_cannot_open_admin_or_school_pages(client):
    make_user("u@x.com", role="user")
    login(client, "u@x.com")
    assert client.get("/dashboard/admin").status_code == 403
    assert client.get("/admin/schools").status_code == 403
    assert client.get("/school/register").status_code == 403


def test_pending_school_is_hidden(client):
    owner = make_user("o@x.com", role="school")
    school = make_school(owner, status="pending")
    assert client.get(f"/schools/{school.id}").status_code == 404


def test_other_school_cannot_download_document(client):
    from app.models import SchoolDocument
    owner = make_user("o@x.com", role="school")
    school = make_school(owner)
    doc = SchoolDocument(school_id=school.id, doc_type="affiliation", original_name="a.pdf",
                         stored_name="abc.pdf", size=10)
    db.session.add(doc)
    db.session.commit()
    make_user("other@x.com", role="school")
    login(client, "other@x.com")
    assert client.get(f"/school/document/{doc.id}").status_code == 403


def test_follow_and_unfollow(client):
    owner = make_user("o@x.com", role="school")
    school = make_school(owner)
    make_user("u@x.com", role="user")
    login(client, "u@x.com")
    r = client.post(f"/schools/{school.id}/follow", follow_redirects=True)
    assert b"You now follow" in r.data
    r = client.post(f"/schools/{school.id}/follow", follow_redirects=True)
    assert b"already follow" in r.data
    r = client.post(f"/schools/{school.id}/unfollow", follow_redirects=True)
    assert b"unfollowed" in r.data


def test_ranking_prefers_matching_school(app):
    from app.matches.scoring import rank_schools
    from app.models import UserPriority
    owner1 = make_user("o1@x.com", role="school")
    owner2 = make_user("o2@x.com", role="school")
    cheap = make_school(owner1, name="Cheap", name_key="cheap", udise_code="11111111111", fee_min=10000)
    make_school(owner2, name="Costly", name_key="costly", udise_code="22222222222", fee_min=90000)
    student = make_user("s@x.com", role="user")
    p = UserPriority(user_id=student.id, max_fee=20000, w_fee=5, w_board=3, w_city=3, w_facilities=3)
    results = rank_schools(p)
    assert results[0]["school"].id == cheap.id
    assert results[0]["score"] == 100
    assert results[1]["score"] < 100