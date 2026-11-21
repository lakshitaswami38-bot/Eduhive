from datetime import datetime

from flask_wtf import FlaskForm
from wtforms import IntegerField, StringField, SubmitField, TextAreaField
from wtforms.fields import DateTimeLocalField
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


class PostForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=150)])
    body = TextAreaField("Post", validators=[DataRequired(), Length(min=10, max=3000)])
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