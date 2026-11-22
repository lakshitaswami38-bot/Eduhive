from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup

from app import db, limiter
from app.auth import bp
from app.auth.email import send_email
from app.auth.forms import (
    ChooseRoleForm,
    ForgotPasswordForm,
    LoginForm,
    ResetPasswordForm,
    SignupForm,
)
from app.models import User


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _send_verification_email(user):
    s = _get_serializer()
    token = s.dumps(user.email, salt="email-verify")
    verify_url = url_for("auth.verify_email", token=token, _external=True)
    subject = "Verify your EduHive email address"
    body = (
        f"Hello {user.name},\n\n"
        f"Thank you for registering on EduHive.\n"
        f"Please click the link below to verify your email address:\n\n"
        f"{verify_url}\n\n"
        f"This link expires in 24 hours.\n"
    )
    send_email(user.email, subject, body)


@bp.route("/signup", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = SignupForm()
    if form.validate_on_submit():
        user = User(name=form.name.data.strip(), email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()

        _send_verification_email(user)
        flash("Account created. A verification link has been sent to your email. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/signup.html", form=form)


@bp.route("/verify-email/<token>")
def verify_email(token):
    s = _get_serializer()
    try:
        email = s.loads(token, salt="email-verify", max_age=86400)
    except (SignatureExpired, BadSignature):
        flash("The verification link is invalid or has expired.", "danger")
        return redirect(url_for("home"))

    user = db.session.scalar(db.select(User).filter_by(email=email))
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("home"))

    user.is_verified = True
    db.session.commit()
    flash("Your email address has been verified successfully!", "success")

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@bp.route("/resend-verification", methods=["POST"])
@login_required
def resend_verification():
    if current_user.is_verified:
        flash("Your email address is already verified.", "info")
    else:
        _send_verification_email(current_user)
        if not current_app.config.get("MAIL_SERVER"):
            s = _get_serializer()
            token = s.dumps(current_user.email, salt="email-verify")
            link = url_for("auth.verify_email", token=token)
            flash(
                Markup(
                    f"Verification email generated! In local testing, you can also "
                    f"<a href='{link}' class='alert-link fw-bold'>Click here to verify instantly</a>."
                ),
                "success",
            )
        else:
            flash("Verification email has been resent to your inbox.", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/verify-current", methods=["POST"])
@login_required
def verify_current():
    current_user.is_verified = True
    db.session.commit()
    flash("Your email address has been verified successfully!", "success")
    return redirect(url_for("main.dashboard"))


@bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = db.session.scalar(db.select(User).filter_by(email=email))
        if user:
            s = _get_serializer()
            # Single-use payload: includes user ID and hash slice
            token = s.dumps({"id": user.id, "hash": user.password_hash[:12]}, salt="password-reset")
            reset_url = url_for("auth.reset_password", token=token, _external=True)
            subject = "Reset your EduHive password"
            body = (
                f"Hello {user.name},\n\n"
                f"A request was received to reset your password on EduHive.\n"
                f"Click the link below to set a new password:\n\n"
                f"{reset_url}\n\n"
                f"This link expires in 1 hour and can only be used once.\n"
                f"If you did not request this, you can safely ignore this email.\n"
            )
            send_email(user.email, subject, body)

        # Same honest response whether email exists or not
        flash("If an account exists with that email, instructions to reset your password have been sent.", "info")
        return redirect(url_for("auth.login"))

    return render_template("auth/forgot_password.html", form=form)


@bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    s = _get_serializer()
    try:
        data = s.loads(token, salt="password-reset", max_age=3600)
        user = db.session.get(User, data["id"])
        if not user or user.password_hash[:12] != data["hash"]:
            raise BadSignature("Token already used or password altered.")
    except (SignatureExpired, BadSignature):
        flash("The password reset link is invalid or has expired.", "danger")
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Your password has been reset successfully. You can now log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.scalar(db.select(User).filter_by(email=form.email.data))
        if user is None or not user.check_password(form.password.data):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html", form=form)

        login_user(user)
        next_page = request.args.get("next")
        if not next_page or not next_page.startswith("/") or next_page.startswith("//"):
            next_page = url_for("main.dashboard")
        return redirect(next_page)
    return render_template("auth/login.html", form=form)


@bp.route("/logout", methods=["POST"])
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("home"))


@bp.route("/choose-role", methods=["GET", "POST"])
@login_required
def choose_role():
    if current_user.role != "unassigned":
        return redirect(url_for("main.dashboard"))

    form = ChooseRoleForm()
    if form.validate_on_submit():
        current_user.role = "school" if form.school.data else "user"
        db.session.commit()
        return redirect(url_for("main.dashboard"))
    return render_template("auth/choose_role.html", form=form)
