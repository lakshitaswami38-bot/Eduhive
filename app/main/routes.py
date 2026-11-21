from flask import redirect, render_template, url_for
from flask_login import current_user, login_required

from app.decorators import role_required
from app.main import bp


@bp.route("/dashboard")
@login_required
def dashboard():
    if current_user.role == "unassigned":
        return redirect(url_for("auth.choose_role"))
    return redirect(url_for(f"main.{current_user.role}_home"))


@bp.route("/dashboard/admin")
@role_required("admin")
def admin_home():
    from app.admin.routes import status_counts
    return render_template("main/admin_home.html", counts=status_counts())


@bp.route("/dashboard/school")
@role_required("school")
def school_home():
    school = current_user.school
    if school is None:
        return redirect(url_for("schools.register"))
    if school.status != "approved":
        return redirect(url_for("schools.status"))
    return render_template("main/school_home.html", school=school)


@bp.route("/dashboard/other")
@role_required("user")
def user_home():
    return render_template("main/user_home.html")