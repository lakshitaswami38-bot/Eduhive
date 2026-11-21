from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from app import limiter
from app import db
from app.auth import bp
from app.auth.forms import ChooseRoleForm, LoginForm, SignupForm
from app.models import User


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
        flash("Account created. Please log in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/signup.html", form=form)


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