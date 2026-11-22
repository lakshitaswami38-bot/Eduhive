from datetime import datetime, timezone
from urllib.parse import urlparse

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired, MultipleFileField
from wtforms import (
    BooleanField,
    DateField,
    FieldList,
    FloatField,
    Form,
    FormField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    NumberRange,
    Optional,
    Regexp,
    URL,
    ValidationError,
)

from app import db
from app.models import School, normalize_name
from app.schools.options import SPECIALITIES
from app.schools.uploads import DOC_TYPES, check_upload

BOARDS = [
    ("", "Select board"),
    ("CBSE", "CBSE"),
    ("ICSE/ISC", "ICSE / ISC"),
    ("State Board", "State Board"),
    ("IB", "IB"),
    ("Cambridge", "Cambridge (IGCSE)"),
    ("Other", "Other"),
]


def valid_year(form, field):
    this_year = datetime.now(timezone.utc).year
    if field.data is None or not (1800 <= field.data <= this_year):
        raise ValidationError(f"Enter a year between 1800 and {this_year}.")


class SchoolForm(FlaskForm):
    name = StringField("School name", validators=[DataRequired(), Length(max=150)])
    udise_code = StringField(
        "UDISE+ code",
        validators=[DataRequired(), Regexp(r"^\d{11}$", message="UDISE+ code must be exactly 11 digits.")],
    )
    board = SelectField("Board", choices=BOARDS, validators=[DataRequired(message="Select a board.")])
    established_year = IntegerField("Year established", validators=[DataRequired(), valid_year])
    address = StringField("Address", validators=[DataRequired(), Length(max=255)])
    city = StringField("City", validators=[DataRequired(), Length(max=80)])
    state = StringField("State", validators=[DataRequired(), Length(max=80)])
    pincode = StringField(
        "Pincode",
        validators=[DataRequired(), Regexp(r"^\d{6}$", message="Pincode must be exactly 6 digits.")],
    )
    principal_phone = StringField(
        "Principal's phone",
        validators=[DataRequired(), Regexp(r"^[6-9]\d{9}$", message="Enter a valid 10 digit mobile number.")],
    )
    official_email = StringField(
        "School's official email",
        validators=[DataRequired(), Email(), Length(max=120)],
        filters=[lambda v: v.strip().lower() if v else v],
    )

    doc_affiliation = FileField("Board affiliation certificate")
    doc_recognition = FileField("State government recognition certificate")
    doc_principal_id = FileField("Principal's ID proof")
    doc_trust = FileField("Society or trust registration certificate")
    doc_address_proof = FileField("Address proof")

    submit = SubmitField("Submit for verification")

    def __init__(self, *args, school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.school = school

    def doc_field(self, key):
        return getattr(self, f"doc_{key}")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        own_id = self.school.id if self.school else None

        # A school can be registered only once.
        if self.udise_code.data and not self.udise_code.errors:
            other = db.session.scalar(db.select(School).filter_by(udise_code=self.udise_code.data))
            if other and other.id != own_id:
                self.udise_code.errors.append("A school with this UDISE+ code is already registered.")
                ok = False

        if self.name.data and self.pincode.data and not self.pincode.errors:
            other = db.session.scalar(
                db.select(School).filter_by(name_key=normalize_name(self.name.data), pincode=self.pincode.data)
            )
            if other and other.id != own_id:
                self.name.errors.append("A school with this name and pincode is already registered.")
                ok = False

        # Documents: check every new upload, and make sure required ones exist.
        for key, _label, required in DOC_TYPES:
            field = self.doc_field(key)
            uploaded = field.data if (field.data and field.data.filename) else None
            if uploaded:
                problem = check_upload(uploaded)
                if problem:
                    field.errors.append(problem)
                    ok = False
            elif required and not (self.school and self.school.document(key)):
                field.errors.append("This document is required.")
                ok = False
        return ok


FACILITIES = [
    ("library", "Library"),
    ("science_lab", "Science labs"),
    ("computer_lab", "Computer lab"),
    ("sports", "Playground / sports"),
    ("transport", "School transport"),
    ("hostel", "Hostel"),
    ("smart_class", "Smart classrooms"),
    ("canteen", "Canteen"),
    ("medical", "Medical room"),
    ("cctv", "CCTV security"),
]

MEDIUMS = [
    ("", "Select medium"),
    ("English", "English"),
    ("Hindi", "Hindi"),
    ("Both", "English and Hindi"),
    ("Other", "Other"),
]


class ResultRowForm(Form):
    """One row of the results table. Plain WTForms Form, so no separate CSRF token per row."""

    year = IntegerField("Year", validators=[Optional()])
    class10 = FloatField("Class 10 pass %", validators=[Optional(), NumberRange(min=0, max=100)])
    class12 = FloatField("Class 12 pass %", validators=[Optional(), NumberRange(min=0, max=100)])


class ProfileForm(FlaskForm):
    about = TextAreaField("About the school", validators=[DataRequired(), Length(min=30, max=2000)])
    medium = SelectField("Medium of teaching", choices=MEDIUMS, validators=[DataRequired(message="Select a medium.")])
    fee_min = IntegerField("Yearly fee, lowest (Rs.)", validators=[DataRequired(), NumberRange(min=0, max=10000000)])
    fee_max = IntegerField("Yearly fee, highest (Rs.)", validators=[DataRequired(), NumberRange(min=0, max=10000000)])
    class_from = IntegerField("Lowest class", validators=[DataRequired(), NumberRange(min=1, max=12)])
    class_to = IntegerField("Highest class", validators=[DataRequired(), NumberRange(min=1, max=12)])
    student_count = IntegerField("Number of students", validators=[DataRequired(), NumberRange(min=1, max=50000)])
    teacher_count = IntegerField("Number of teachers", validators=[DataRequired(), NumberRange(min=1, max=5000)])
    facilities = SelectMultipleField("Facilities", choices=FACILITIES)
    specialities = SelectMultipleField("Specialities", choices=SPECIALITIES)
    results = FieldList(FormField(ResultRowForm), min_entries=3, max_entries=3)
    website = StringField("Website (optional)", validators=[Optional(), URL(), Length(max=200)])

    admission_open = BooleanField("Admissions are currently open")
    admission_deadline = DateField("Last date to apply", validators=[Optional()])
    admission_url = StringField("Admission link (optional)", validators=[Optional(), Length(max=300)])

    latitude = FloatField("Latitude", validators=[Optional()])
    longitude = FloatField("Longitude", validators=[Optional()])
    redetect = BooleanField("Detect the location again from my address")

    submit = SubmitField("Save profile")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if self.fee_min.data is not None and self.fee_max.data is not None and self.fee_max.data < self.fee_min.data:
            self.fee_max.errors.append("Highest fee cannot be less than the lowest fee.")
            ok = False
        if self.class_from.data is not None and self.class_to.data is not None and self.class_to.data < self.class_from.data:
            self.class_to.errors.append("Highest class cannot be lower than the lowest class.")
            ok = False

        url = (self.admission_url.data or "").strip()
        if url:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                self.admission_url.errors.append("Enter a valid link starting with http:// or https://")
                ok = False

        this_year = datetime.now(timezone.utc).year
        seen_years = set()
        for row in self.results:
            year, c10, c12 = row.year.data, row.class10.data, row.class12.data
            if c10 is None and c12 is None:
                if year is not None:
                    row.class10.errors.append("Enter at least one pass percentage.")
                    ok = False
                continue
            if year is None or not (1990 <= year <= this_year):
                row.year.errors.append(f"Enter a year between 1990 and {this_year}.")
                ok = False
            elif year in seen_years:
                row.year.errors.append("This year is entered twice.")
                ok = False
            else:
                seen_years.add(year)

        lat, lng = self.latitude.data, self.longitude.data
        if (lat is None) != (lng is None):
            self.longitude.errors.append("Enter both latitude and longitude, or leave both empty.")
            ok = False
        elif lat is not None and not (6.0 <= lat <= 37.5 and 68.0 <= lng <= 97.5):
            self.latitude.errors.append("The location must be inside India (latitude 6 to 37.5, longitude 68 to 97.5).")
            ok = False

        return ok


class LogoForm(FlaskForm):
    logo = FileField(
        "School logo",
        validators=[
            FileRequired(message="Choose a logo file to upload."),
            FileAllowed(["jpg", "jpeg", "png"], "Only JPG or PNG files are allowed."),
        ],
    )
    submit = SubmitField("Upload logo")


class GalleryForm(FlaskForm):
    photos = MultipleFileField("Gallery photos")
    submit = SubmitField("Upload photos")


class InquiryForm(FlaskForm):
    child_class = IntegerField("Class applying for", validators=[DataRequired(), NumberRange(min=1, max=12)])
    message = TextAreaField("Your message / inquiry", validators=[DataRequired(), Length(min=10, max=2000)])
    submit = SubmitField("Submit Inquiry")


class InquiryReplyForm(FlaskForm):
    reply = TextAreaField("Reply message", validators=[DataRequired(), Length(min=5, max=2000)])
    submit = SubmitField("Send Reply")
