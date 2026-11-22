from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FloatField,
    HiddenField,
    IntegerField,
    SelectField,
    SelectMultipleField,
    StringField,
    SubmitField,
)
from wtforms.validators import Length, NumberRange, Optional

from app.schools.forms import BOARDS, FACILITIES
from app.schools.options import SPECIALITIES

BOARD_CHOICES = [("", "Any board")] + BOARDS[1:]
WEIGHTS = [(1, "Not important"), (2, "Slightly"), (3, "Important"), (4, "Very important"), (5, "Most important")]


class PriorityForm(FlaskForm):
    max_fee = IntegerField("Maximum yearly fee (Rs.)", validators=[Optional(), NumberRange(min=0, max=10000000)])
    board = SelectField("Board", choices=BOARD_CHOICES)
    city = StringField("City", validators=[Optional(), Length(max=80)])
    class_needed = IntegerField("Class your child needs (1 to 12)", validators=[Optional(), NumberRange(min=1, max=12)])
    facilities = SelectMultipleField("Facilities you want", choices=FACILITIES)
    specialities = SelectMultipleField("Specialities / Focus areas", choices=SPECIALITIES)

    # Location & Distance
    max_distance = IntegerField("Max distance from you (km)", validators=[Optional(), NumberRange(min=1, max=100)])
    pincode = StringField("Pincode (for distance calculation)", validators=[Optional(), Length(max=10)])
    latitude = HiddenField()
    longitude = HiddenField()

    # Hard filter
    admission_only = BooleanField("Show only schools with admissions currently open")

    # Importance weights (1 to 5)
    w_fee = SelectField("How important is fee?", choices=WEIGHTS, coerce=int, default=3)
    w_board = SelectField("How important is board?", choices=WEIGHTS, coerce=int, default=3)
    w_city = SelectField("How important is city?", choices=WEIGHTS, coerce=int, default=3)
    w_facilities = SelectField("How important are facilities?", choices=WEIGHTS, coerce=int, default=3)
    w_specialities = SelectField("How important are specialities?", choices=WEIGHTS, coerce=int, default=3)
    w_results = SelectField("How important are board exam results?", choices=WEIGHTS, coerce=int, default=3)
    w_distance = SelectField("How important is distance?", choices=WEIGHTS, coerce=int, default=3)

    submit = SubmitField("Save and see matches")
