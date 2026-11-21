from datetime import datetime, timezone

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.admin import bp
from app.admin.forms import RejectForm
from app.decorators import role_required
from app.models import School
from app.schools.uploads import DOC_TYPES

STATUSES = ("pending", "approved", "rejected")


def status_counts():
    rows = db.session.execute(db.select(School.status, func.count()).group_by(School.status)).all()
    counts = {s: 0 for s in STATUSES}
    counts.update({status: n for status, n in rows})
    return counts


@bp.route("/schools")
@role_required("admin")
def schools():
    status = request.args.get("status", "pending")
    query = db.select(School).order_by(School.submitted_at.desc())
    if status in STATUSES:
        query = query.filter_by(status=status)
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