from datetime import datetime, timezone

from flask import abort, flash, redirect, render_template, request, send_from_directory, url_for, current_app
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from app.schools.forms import FACILITIES, ProfileForm, SchoolForm
from sqlalchemy import func

from app.models import Follow

from app import db
from app.decorators import role_required

from app.models import Event, Post, School, SchoolDocument, normalize_name
from app.schools import bp
from app.schools.uploads import DOC_TYPES, delete_upload, save_upload

FIELDS = [
    "name", "udise_code", "board", "established_year", "address",
    "city", "state", "pincode", "principal_phone", "official_email",
]


def _fill(school, form):
    for field in FIELDS:
        value = getattr(form, field).data
        setattr(school, field, value.strip() if isinstance(value, str) else value)
    school.name_key = normalize_name(school.name)


def _store_documents(school, form):
    """Save new uploads. Returns (new_stored_names, old_stored_names_to_delete)."""
    new_files, old_files = [], []
    for key, _label, _required in DOC_TYPES:
        storage = form.doc_field(key).data
        if not (storage and storage.filename):
            continue
        stored, original, size = save_upload(storage)
        new_files.append(stored)
        existing = school.document(key)
        if existing:
            old_files.append(existing.stored_name)
            existing.original_name, existing.stored_name, existing.size = original, stored, size
            existing.uploaded_at = datetime.now(timezone.utc)
        else:
            school.documents.append(
                SchoolDocument(doc_type=key, original_name=original, stored_name=stored, size=size)
            )
    return new_files, old_files


def _save_application(school, form, is_new):
    new_files = []
    try:
        _fill(school, form)
        school.status = "pending"
        school.rejection_reason = None
        school.reviewed_at = None
        school.reviewed_by_id = None
        school.submitted_at = datetime.now(timezone.utc)
        if is_new:
            db.session.add(school)
            db.session.flush()
        new_files, old_files = _store_documents(school, form)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        for name in new_files:
            delete_upload(name)
        return False
    except Exception:
        db.session.rollback()
        for name in new_files:
            delete_upload(name)
        raise
    for name in old_files:
        delete_upload(name)
    return True


@bp.route("/school/register", methods=["GET", "POST"])
@role_required("school")
def register():
    if current_user.school:
        return redirect(url_for("schools.status"))

    form = SchoolForm()
    if form.validate_on_submit():
        school = School(owner_id=current_user.id)
        if _save_application(school, form, is_new=True):
            flash("Application submitted. An admin will review it soon.", "success")
            return redirect(url_for("schools.status"))
        flash("A school with these details is already registered.", "danger")
    return render_template("schools/form.html", form=form, mode="register", school=None, doc_types=DOC_TYPES)


@bp.route("/school/status")
@role_required("school")
def status():
    school = current_user.school
    if school is None:
        return redirect(url_for("schools.register"))
    return render_template("schools/status.html", school=school, doc_types=DOC_TYPES)


@bp.route("/school/edit", methods=["GET", "POST"])
@role_required("school")
def edit():
    school = current_user.school
    if school is None:
        return redirect(url_for("schools.register"))
    if school.status != "rejected":
        flash("You can edit the application only after it has been rejected.", "info")
        return redirect(url_for("schools.status"))

    form = SchoolForm(obj=school, school=school)
    if form.validate_on_submit():
        if _save_application(school, form, is_new=False):
            flash("Application updated and sent for review again.", "success")
            return redirect(url_for("schools.status"))
        flash("A school with these details is already registered.", "danger")
    return render_template("schools/form.html", form=form, mode="edit", school=school, doc_types=DOC_TYPES)


@bp.route("/school/document/<int:doc_id>")
@login_required
def document(doc_id):
    doc = db.get_or_404(SchoolDocument, doc_id)
    if current_user.role != "admin" and doc.school.owner_id != current_user.id:
        abort(403)
    response = send_from_directory(
        current_app.config["UPLOAD_FOLDER"], doc.stored_name, download_name=doc.original_name
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@bp.route("/school/profile", methods=["GET", "POST"])
@role_required("school")
def profile():
    school = current_user.school
    if school is None or school.status != "approved":
        flash("You can fill the profile after your school is approved.", "info")
        return redirect(url_for("schools.status"))

    form = ProfileForm(obj=school)
    if request.method == "GET":
        form.facilities.data = school.facility_list
    if form.validate_on_submit():
        for name in ("about", "medium", "fee_min", "fee_max", "class_from", "class_to",
                    "student_count", "teacher_count"):
            setattr(school, name, getattr(form, name).data)
        school.about = school.about.strip()
        school.website = (form.website.data or "").strip() or None
        school.facilities = ",".join(form.facilities.data)
        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("schools.public", school_id=school.id))
    return render_template("schools/profile.html", form=form)


@bp.route("/schools")
def listing():
    q = request.args.get("q", "").strip()
    board = request.args.get("board", "").strip()
    max_fee = request.args.get("max_fee", type=int)

    query = db.select(School).filter_by(status="approved").order_by(School.name)
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(School.name.ilike(like), School.city.ilike(like)))
    if board:
        query = query.filter_by(board=board)
    if max_fee is not None:
        query = query.filter(School.fee_min <= max_fee)

    schools = db.session.scalars(query).all()
    return render_template("schools/list.html", schools=schools, q=q, board=board, max_fee=max_fee)


@bp.route("/schools/<int:school_id>")
def public(school_id):
    school = db.get_or_404(School, school_id)
    allowed = school.status == "approved" or (
        current_user.is_authenticated
        and (current_user.role == "admin" or school.owner_id == current_user.id)
    )
    if not allowed:
        abort(404)
    labels = dict(FACILITIES)
    facilities = [labels[f] for f in school.facility_list if f in labels]
    posts = db.session.scalars(
        db.select(Post).filter_by(school_id=school.id).order_by(Post.created_at.desc()).limit(10)
    ).all()
    events = db.session.scalars(
        db.select(Event)
        .filter(Event.school_id == school.id, Event.starts_at >= datetime.now())
        .order_by(Event.starts_at)
    ).all()
    followers = db.session.scalar(
        db.select(func.count()).select_from(Follow).filter_by(school_id=school.id)
    )
    following = bool(
        current_user.is_authenticated
        and current_user.role == "user"
        and db.session.scalar(
            db.select(Follow).filter_by(user_id=current_user.id, school_id=school.id)
        )
    )
    return render_template(
        "schools/detail.html", school=school, facilities=facilities, posts=posts,
        events=events, followers=followers, following=following,
    )