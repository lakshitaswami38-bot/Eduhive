from flask_wtf import FlaskForm
from wtforms import SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class RejectForm(FlaskForm):
    reason = TextAreaField(
        "Reason for rejection",
        validators=[DataRequired(), Length(min=10, max=1000, message="Give a clear reason (10 to 1000 characters).")],
    )
    submit = SubmitField("Reject application")