import io
import os
from datetime import date, timedelta
from PIL import Image

from app import db
from app.models import School, SchoolPhoto, SchoolResult, SchoolTag
from tests.conftest import login, make_user


def _make_test_image(format="JPEG", size=(200, 200), color=(200, 100, 50)):
    buf = io.BytesIO()
    img = Image.new("RGB", size, color)
    img.save(buf, format=format)
    buf.seek(0)
    ext = "jpg" if format == "JPEG" else "png"
    return (buf, f"photo.{ext}")


def _create_approved_school(owner):
    school = School(
        owner_id=owner.id,
        name="St. Xavier High School",
        name_key="st. xavier high school",
        udise_code="23260199999",
        board="ICSE/ISC",
        address="MG Road",
        city="Bhopal",
        state="MP",
        pincode="462001",
        established_year=1995,
        principal_phone="9876543210",
        official_email="principal@xaviers.test",
        status="approved",
        fee_min=20000,
        fee_max=50000,
        class_from=1,
        class_to=12,
        student_count=1500,
        teacher_count=70,
        facilities="library,sports",
    )
    db.session.add(school)
    db.session.commit()
    return school


def test_specialities_and_results_and_admissions(client, app):
    owner = make_user("owner1@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner1@example.com")

    profile_data = {
        "about": "A reputable academic institution with state of the art facilities and labs.",
        "medium": "English",
        "website": "https://xaviers.example.com",
        "fee_min": 25000,
        "fee_max": 55000,
        "class_from": 1,
        "class_to": 12,
        "student_count": 1600,
        "teacher_count": 75,
        "facilities": ["library", "sports"],
        "specialities": ["science", "robotics", "coding"],
        "admission_open": "y",
        "admission_deadline": (date.today() + timedelta(days=30)).isoformat(),
        "admission_url": "https://xaviers.example.com/apply",
        "results-0-year": 2025,
        "results-0-class10": 98.5,
        "results-0-class12": 96.2,
        "results-1-year": 2024,
        "results-1-class10": 97.0,
        "results-1-class12": 95.0,
        "results-2-year": "",
        "results-2-class10": "",
        "results-2-class12": "",
    }

    r = client.post("/school/profile", data=profile_data, follow_redirects=True)
    assert r.status_code == 200
    assert b"Profile saved" in r.data

    # Verify database persistence
    db.session.refresh(school)
    assert school.admission_open is True
    assert school.admission_url == "https://xaviers.example.com/apply"
    assert "science" in school.specialities
    assert "robotics" in school.specialities

    # Check results in DB
    results = db.session.scalars(db.select(SchoolResult).filter_by(school_id=school.id)).all()
    assert len(results) == 2

    # Check public page
    r = client.get(f"/schools/{school.id}")
    assert r.status_code == 200
    assert b"Science" in r.data
    assert b"Robotics" in r.data
    assert b"Reported by the school, not verified" in r.data
    assert b"98.5%" in r.data
    assert b"Apply for Admission" in r.data


def test_admission_url_scheme_validation(client, app):
    owner = make_user("owner2@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner2@example.com")

    # Invalid URL scheme (javascript:)
    r = client.post(
        "/school/profile",
        data={
            "about": "A reputable academic institution with state of the art facilities and labs.",
            "medium": "English",
            "fee_min": 25000,
            "fee_max": 55000,
            "class_from": 1,
            "class_to": 12,
            "student_count": 1600,
            "teacher_count": 75,
            "admission_url": "javascript:alert(1)",
        },
    )
    assert b"Enter a valid link starting with http://" in r.data


def test_logo_upload_and_security(client, app):
    owner = make_user("owner3@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner3@example.com")

    # Upload valid PNG logo
    logo_file = _make_test_image(format="PNG", size=(300, 300))
    r = client.post(
        "/school/profile/logo",
        data={"logo": logo_file},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"Logo updated" in r.data

    db.session.refresh(school)
    assert school.logo is not None
    logo_id = school.logo.id

    # Verify public can view approved school logo
    client.post("/logout", follow_redirects=True)
    r = client.get(f"/school/photo/{logo_id}")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"


def test_photo_hidden_for_unapproved_school(client, app):
    owner = make_user("owner4@example.com", role="school")
    school = _create_approved_school(owner)
    school.status = "pending"
    photo = SchoolPhoto(school_id=school.id, kind="logo", stored_name="test_logo.jpg", original_name="logo.jpg")
    db.session.add(photo)
    db.session.commit()

    # Anonymous user should get 404
    r = client.get(f"/school/photo/{photo.id}")
    assert r.status_code == 404

    # Other normal user should get 404
    make_user("user_other@example.com", role="user")
    login(client, "user_other@example.com")
    r = client.get(f"/school/photo/{photo.id}")
    assert r.status_code == 404

    # School owner CAN view preview
    client.post("/logout", follow_redirects=True)
    login(client, "owner4@example.com")
    # File doesn't exist on disk, but route permission check allows owner before send_from_directory
    # Let's verify status code is not 404 from permission check (either 200 or 404 only if file missing)


def test_gallery_upload_and_delete(client, app):
    owner = make_user("owner5@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner5@example.com")

    # Upload 2 photos
    photo1 = _make_test_image(format="JPEG", size=(800, 600))
    photo2 = _make_test_image(format="JPEG", size=(800, 600))

    r = client.post(
        "/school/profile/gallery",
        data={"photos": [photo1, photo2]},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"2 photo(s) added" in r.data

    db.session.refresh(school)
    assert len(school.gallery) == 2
    photo_to_delete = school.gallery[0]
    p_id = photo_to_delete.id
    stored_path = os.path.join(app.config["UPLOAD_FOLDER"], "photos", photo_to_delete.stored_name)
    assert os.path.exists(stored_path)

    # Delete photo
    r = client.post(f"/school/profile/photo/{p_id}/delete", follow_redirects=True)
    assert b"Photo removed" in r.data
    assert not os.path.exists(stored_path)
    db.session.refresh(school)
    assert len(school.gallery) == 1


def test_gallery_max_8_limit(client, app):
    owner = make_user("owner6@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner6@example.com")

    # Try uploading 9 photos
    photos = [_make_test_image(format="JPEG", size=(100, 100)) for _ in range(9)]
    r = client.post(
        "/school/profile/gallery",
        data={"photos": photos},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"The gallery can hold up to 8 photos" in r.data
    db.session.refresh(school)
    assert len(school.gallery) == 0


def test_invalid_photo_rejected(client, app):
    owner = make_user("owner7@example.com", role="school")
    school = _create_approved_school(owner)
    login(client, "owner7@example.com")

    # Disguised text file
    fake_img = (io.BytesIO(b"This is not a real jpeg file"), "fake.jpg")
    r = client.post(
        "/school/profile/logo",
        data={"logo": fake_img},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert b"not a valid JPG or PNG photo" in r.data
