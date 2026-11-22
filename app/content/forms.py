from datetime import datetime

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import IntegerField, StringField, SubmitField, TextAreaField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=150)])
    body = TextAreaField("Post", validators=[DataRequired(), Length(min=10, max=3000)])
    photo = FileField(
        "Photo (optional, max 5 MB)",
        validators=[Optional(), FileAllowed(["jpg", "jpeg", "png"], "Only JPG or PNG images are allowed.")],
    )
    submit = SubmitField("Publish post")


class EventForm(FlaskForm):
    title = StringField("Event title", validators=[DataRequired(), Length(max=150)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=10, max=2000)])
    venue = StringField("Venue", validators=[DataRequired(), Length(max=200)])
    starts_at = DateTimeLocalField(
        "Date and time", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    capacity = IntegerField(
        "Seats (leave empty for unlimited)", validators=[Optional(), NumberRange(min=1, max=100000)]
    )
    submit = SubmitField("Publish event")

    def validate_starts_at(self, field):
        if field.data and field.data <= datetime.now():
            raise ValidationError("The event must be in the future.")


class EventRegisterForm(FlaskForm):
    participants = IntegerField(
        "Number of attendees",
        validators=[DataRequired(), NumberRange(min=1, max=50, message="Attendees must be between 1 and 50.")],
        default=1,
    )
    note = StringField("Note / remarks (optional)", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Register")
