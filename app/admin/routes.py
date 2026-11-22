from datetime import datetime, timezone
from urllib.parse import urlparse

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.admin import bp
from app.admin.forms import RejectForm
from app.decorators import role_required
from app.models import Post, School, User
from app.schools.images import delete_image
from app.schools.uploads import DOC_TYPES

STATUSES = ("pending", "approved", "rejected", "suspended")


def status_counts():
    counts = {s: 0 for s in STATUSES}
    for status, in db.session.execute(db.select(School.status)).all():
        if status in counts:
            counts[status] += 1
    suspended_count = db.session.scalar(
        db.select(func.count()).select_from(School).filter_by(is_suspended=True)
    )
    counts["suspended"] = suspended_count or 0
    return counts


@bp.route("/schools")
@role_required("admin")
def schools():
    status = request.args.get("status", "pending")
    query = db.select(School).order_by(School.submitted_at.desc())

    if status == "suspended":
        query = query.filter_by(is_suspended=True)
    elif status in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status, is_suspended=False)
    else:
        status = "all"

    return render_template(
        "admin/schools.html",
        schools=db.session.scalars(query).all(),
        counts=status_counts(),
        current=status,
    )


@bp.route("/schools/<int:school_id>")
@role_required("admin")
def detail(school_id):
    school = db.get_or_404(School, school_id)
    return render_template("admin/school_detail.html", school=school, doc_types=DOC_TYPES, form=RejectForm())


@bp.route("/schools/<int:school_id>/approve", methods=["POST"])
@role_required("admin")
def approve(school_id):
    school = db.get_or_404(School, school_id)
    if school.status != "pending":
        flash("Only pending applications can be approved.", "warning")
    else:
        school.status = "approved"
        school.rejection_reason = None
        school.reviewed_at = datetime.now(timezone.utc)
        school.reviewed_by_id = current_user.id
        db.session.commit()
        flash(f"{school.name} has been approved.", "success")
    return redirect(url_for("admin.detail", school_id=school.id))


@bp.route("/schools/<int:school_id>/reject", methods=["POST"])
@role_required("admin")
def reject(school_id):
    school = db.get_or_404(School, school_id)
    form = RejectForm()
    if school.status != "pending":
        flash("Only pending applications can be rejected.", "warning")
        return redirect(url_for("admin.detail", school_id=school.id))
    if form.validate_on_submit():
        school.status = "rejected"
        school.rejection_reason = form.reason.data.strip()
        school.reviewed_at = datetime.now(timezone.utc)
        school.reviewed_by_id = current_user.id
        db.session.commit()
        flash(f"{school.name} has been rejected.", "info")
        return redirect(url_for("admin.detail", school_id=school.id))
    return render_template("admin/school_detail.html", school=school, doc_types=DOC_TYPES, form=form)


@bp.route("/schools/<int:school_id>/suspend", methods=["POST"])
@role_required("admin")
def suspend(school_id):
    school = db.get_or_404(School, school_id)
    school.is_suspended = True
    db.session.commit()
    flash(f"{school.name} has been suspended. It will not appear in public listings.", "warning")
    return redirect(url_for("admin.detail", school_id=school.id))


@bp.route("/schools/<int:school_id>/reinstate", methods=["POST"])
@role_required("admin")
def reinstate(school_id):
    school = db.get_or_404(School, school_id)
    school.is_suspended = False
    db.session.commit()
    flash(f"{school.name} has been reinstated to public listings.", "success")
    return redirect(url_for("admin.detail", school_id=school.id))


@bp.route("/users")
@role_required("admin")
def users():
    role_filter = request.args.get("role", "all")
    query = db.select(User).order_by(User.created_at.desc())
    if role_filter in ("unassigned", "user", "school", "admin"):
        query = query.filter_by(role=role_filter)
    else:
        role_filter = "all"

    all_users = db.session.scalars(query).all()
    return render_template("admin/users.html", users=all_users, current_role=role_filter)


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@role_required("admin")
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    school_id = post.school_id
    if post.photo_name:
        delete_image(post.photo_name)
    db.session.delete(post)
    db.session.commit()
    flash("Post removed by administrator.", "info")

    referrer = request.referrer
    if referrer:
        parsed = urlparse(referrer)
        if not parsed.netloc and not referrer.startswith("//"):
            return redirect(referrer)
    return redirect(url_for("schools.public", school_id=school_id))
