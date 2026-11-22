from flask import flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.decorators import role_required
from app.main import bp
from app.models import Follow, Post, School


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
        if not current_user.is_verified:
            flash("Please verify your email address before registering your school.", "warning")
            return render_template("main/school_home.html", school=None)
        return redirect(url_for("schools.register"))
    if school.status != "approved":
        return redirect(url_for("schools.status"))

    posts = db.session.scalars(
        db.select(Post).filter_by(school_id=school.id).order_by(Post.created_at.desc()).limit(10)
    ).all()
    return render_template("main/school_home.html", school=school, posts=posts)


@bp.route("/dashboard/other")
@role_required("user")
def user_home():
    followed_ids = db.session.scalars(
        db.select(Follow.school_id).filter_by(user_id=current_user.id)
    ).all()
    if followed_ids:
        posts = db.session.scalars(
            db.select(Post).filter(Post.school_id.in_(followed_ids)).order_by(Post.created_at.desc()).limit(10)
        ).all()
        feed_type = "following"
    else:
        posts = db.session.scalars(
            db.select(Post).join(School).filter(School.status == "approved", School.is_suspended == False).order_by(Post.created_at.desc()).limit(10)
        ).all()
        feed_type = "discover"
    return render_template("main/user_home.html", posts=posts, feed_type=feed_type, following_count=len(followed_ids))