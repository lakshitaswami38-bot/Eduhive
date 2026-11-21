from wtforms import SelectMultipleField, TextAreaField
from wtforms.validators import NumberRange, Optional, URL
from datetime import datetime, timezone

from flask_wtf import FlaskForm
from flask_wtf.file import FileField
from wtforms import IntegerField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Regexp, ValidationError

from app import db
from app.models import School, normalize_name
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
        self.school = school  # the school being edited, or None when registering

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
    ("library", "Library"), ("science_lab", "Science labs"), ("computer_lab", "Computer lab"),
    ("sports", "Playground / sports"), ("transport", "School transport"), ("hostel", "Hostel"),
    ("smart_class", "Smart classrooms"), ("canteen", "Canteen"), ("medical", "Medical room"),
    ("cctv", "CCTV security"),
]
MEDIUMS = [("", "Select medium"), ("English", "English"), ("Hindi", "Hindi"),
        ("Both", "English and Hindi"), ("Other", "Other")]


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
    website = StringField("Website (optional)", validators=[Optional(), URL(), Length(max=200)])
    submit = SubmitField("Save profile")

    def validate(self, extra_validators=None):
        ok = super().validate(extra_validators=extra_validators)
        if self.fee_min.data is not None and self.fee_max.data is not None \
                and self.fee_max.data < self.fee_min.data:
            self.fee_max.errors.append("Highest fee cannot be less than the lowest fee.")
            ok = False
        if self.class_from.data is not None and self.class_to.data is not None \
                and self.class_to.data < self.class_from.data:
            self.class_to.errors.append("Highest class cannot be lower than the lowest class.")
            ok = False
        return ok
