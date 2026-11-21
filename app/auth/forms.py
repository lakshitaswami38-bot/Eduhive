from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app import db
from app.models import User


def clean_email(value):
    return value.strip().lower() if value else value


class SignupForm(FlaskForm):
    name = StringField("Full name", validators=[DataRequired(), Length(max=100)])
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=120)],
        filters=[clean_email],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords must match.")],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field):
        if db.session.scalar(db.select(User).filter_by(email=field.data)):
            raise ValidationError("This email is already registered.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()], filters=[clean_email])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class ChooseRoleForm(FlaskForm):
    school = SubmitField("Register my school")
    other = SubmitField("Continue as student, parent or teacher")