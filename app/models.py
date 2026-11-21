from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="unassigned")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def normalize_name(name):
    """'  St.  Mary's   School ' -> "st. mary's school" (used to detect duplicates)."""
    return " ".join((name or "").lower().split())


class School(db.Model):
    __tablename__ = "schools"
    __table_args__ = (
        db.UniqueConstraint("name_key", "pincode", name="uq_school_name_pincode"),
    )

    id = db.Column(db.Integer, primary_key=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    name = db.Column(db.String(150), nullable=False)
    name_key = db.Column(db.String(150), nullable=False)
    udise_code = db.Column(db.String(11), unique=True, nullable=False)
    board = db.Column(db.String(40), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    pincode = db.Column(db.String(6), nullable=False)
    established_year = db.Column(db.Integer, nullable=False)
    principal_phone = db.Column(db.String(15), nullable=False)
    official_email = db.Column(db.String(120), nullable=False)

    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    rejection_reason = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    reviewed_at = db.Column(db.DateTime)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    about = db.Column(db.Text)
    medium = db.Column(db.String(40))
    fee_min = db.Column(db.Integer)
    fee_max = db.Column(db.Integer)
    class_from = db.Column(db.Integer)
    class_to = db.Column(db.Integer)
    student_count = db.Column(db.Integer)
    teacher_count = db.Column(db.Integer)
    facilities = db.Column(db.String(255))
    website = db.Column(db.String(200))

    owner = db.relationship(
        "User", foreign_keys=[owner_id], backref=db.backref("school", uselist=False)
    )
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])
    documents = db.relationship(
        "SchoolDocument", backref="school", cascade="all, delete-orphan"
    )

    @property
    def years_running(self):
        return max(0, datetime.now(timezone.utc).year - self.established_year)

    @property
    def facility_list(self):
        return [f for f in (self.facilities or "").split(",") if f]

    def document(self, doc_type):
        return next((d for d in self.documents if d.doc_type == doc_type), None)


class SchoolDocument(db.Model):
    __tablename__ = "school_documents"
    __table_args__ = (
        db.UniqueConstraint("school_id", "doc_type", name="uq_school_doctype"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    doc_type = db.Column(db.String(30), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(100), unique=True, nullable=False)
    size = db.Column(db.Integer, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------
# Older design (not used by M3 to M6 code). Kept so that the next
# migration does not try to drop these tables.
# ---------------------------------------------------------------
class SchoolProfile(db.Model):
    __tablename__ = "school_profiles"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), unique=True, nullable=False)

    tagline = db.Column(db.String(150))
    about = db.Column(db.Text)
    medium = db.Column(db.String(20))
    classes_from = db.Column(db.String(10))
    classes_to = db.Column(db.String(10))
    total_students = db.Column(db.Integer)

    fee_min = db.Column(db.Integer)
    fee_max = db.Column(db.Integer)

    admission_open = db.Column(db.Boolean, nullable=False, default=False)
    admission_deadline = db.Column(db.Date)
    admission_url = db.Column(db.String(300))

    latitude = db.Column(db.Float(53))
    longitude = db.Column(db.Float(53))
    location_source = db.Column(db.String(10))  # address, pincode or manual
    geocode_key = db.Column(db.String(400))

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    school = db.relationship(
        "School", backref=db.backref("profile", uselist=False, cascade="all, delete-orphan")
    )


class SchoolTag(db.Model):
    """One facility or speciality of a school (older design)."""

    __tablename__ = "school_tags"
    __table_args__ = (
        db.UniqueConstraint("school_id", "kind", "value", name="uq_school_tag"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    kind = db.Column(db.String(15), nullable=False)  # facility or speciality
    value = db.Column(db.String(30), nullable=False)

    school = db.relationship("School", backref=db.backref("tags", cascade="all, delete-orphan"))


class SchoolResult(db.Model):
    """Board exam pass percentages, reported by the school itself."""

    __tablename__ = "school_results"
    __table_args__ = (
        db.UniqueConstraint("school_id", "year", name="uq_school_result_year"),
    )

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    year = db.Column(db.Integer, nullable=False)
    class10_pass = db.Column(db.Numeric(5, 2))
    class12_pass = db.Column(db.Numeric(5, 2))

    school = db.relationship("School", backref=db.backref("results", cascade="all, delete-orphan"))


class SchoolPhoto(db.Model):
    __tablename__ = "school_photos"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False)  # logo or gallery
    stored_name = db.Column(db.String(100), unique=True, nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    school = db.relationship("School", backref=db.backref("photos", cascade="all, delete-orphan"))


# Read-only shortcuts for the older design (School.facilities is a real column now,
# so it is NOT redefined here).
School.specialities = property(lambda self: sorted(t.value for t in self.tags if t.kind == "speciality"))
School.logo = property(lambda self: next((p for p in self.photos if p.kind == "logo"), None))
School.gallery = property(lambda self: [p for p in self.photos if p.kind == "gallery"])


class Post(db.Model):
    __tablename__ = "posts"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    school = db.relationship("School", backref=db.backref("posts", cascade="all, delete-orphan"))


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=False)
    venue = db.Column(db.String(200), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)  # local time as entered
    capacity = db.Column(db.Integer)  # None = unlimited
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    school = db.relationship("School", backref=db.backref("events", cascade="all, delete-orphan"))
    registrations = db.relationship(
        "EventRegistration", backref="event", cascade="all, delete-orphan"
    )

    @property
    def is_past(self):
        return self.starts_at < datetime.now()

    @property
    def spots_left(self):
        if self.capacity is None:
            return None
        return max(0, self.capacity - len(self.registrations))


class EventRegistration(db.Model):
    __tablename__ = "event_registrations"
    __table_args__ = (
        db.UniqueConstraint("event_id", "user_id", name="uq_event_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class UserPriority(db.Model):
    __tablename__ = "user_priorities"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)

    max_fee = db.Column(db.Integer)
    board = db.Column(db.String(40))
    city = db.Column(db.String(80))
    class_needed = db.Column(db.Integer)
    facilities = db.Column(db.String(255))

    w_fee = db.Column(db.Integer, nullable=False, default=3)
    w_board = db.Column(db.Integer, nullable=False, default=3)
    w_city = db.Column(db.Integer, nullable=False, default=3)
    w_facilities = db.Column(db.Integer, nullable=False, default=3)
    updated_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    user = db.relationship("User", backref=db.backref("priority", uselist=False))

    @property
    def facility_list(self):
        return [f for f in (self.facilities or "").split(",") if f]


class Follow(db.Model):
    __tablename__ = "follows"
    __table_args__ = (
        db.UniqueConstraint("user_id", "school_id", name="uq_follow_user_school"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    school_id = db.Column(db.Integer, db.ForeignKey("schools.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    school = db.relationship("School", backref=db.backref("followers", cascade="all, delete-orphan"))
    user = db.relationship("User", backref=db.backref("follows", cascade="all, delete-orphan"))