from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, SelectMultipleField, StringField, SubmitField
from wtforms.validators import Length, NumberRange, Optional

from app.schools.forms import BOARDS, FACILITIES

BOARD_CHOICES = [("", "Any board")] + BOARDS[1:]
WEIGHTS = [(1, "Not important"), (2, "Slightly"), (3, "Important"), (4, "Very important"), (5, "Most important")]


class PriorityForm(FlaskForm):
    max_fee = IntegerField("Maximum yearly fee (Rs.)", validators=[Optional(), NumberRange(min=0, max=10000000)])
    board = SelectField("Board", choices=BOARD_CHOICES)
    city = StringField("City", validators=[Optional(), Length(max=80)])
    class_needed = IntegerField("Class your child needs (1 to 12)", validators=[Optional(), NumberRange(min=1, max=12)])
    facilities = SelectMultipleField("Facilities you want", choices=FACILITIES)

    w_fee = SelectField("How important is fee?", choices=WEIGHTS, coerce=int, default=3)
    w_board = SelectField("How important is board?", choices=WEIGHTS, coerce=int, default=3)
    w_city = SelectField("How important is city?", choices=WEIGHTS, coerce=int, default=3)
    w_facilities = SelectField("How important are facilities?", choices=WEIGHTS, coerce=int, default=3)
    submit = SubmitField("Save and see matches")