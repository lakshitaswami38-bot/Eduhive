from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app import db
from app.decorators import role_required
from app.models import (
    AdmissionInquiry,
    Connection,
    Event,
    Follow,
    Post,
    School,
    SchoolDocument,
    SchoolPhoto,
    SchoolResult,
    SchoolTag,
    UserShortlist,
    normalize_name,
)
from app.schools import bp
from app.schools.forms import (
    FACILITIES,
    GalleryForm,
    InquiryForm,
    InquiryReplyForm,
    LogoForm,
    ProfileForm,
    SchoolForm,
)
from app.schools.geocode import geocode_pincode, haversine_distance
from app.schools.images import (
    ImageError,
    delete_image,
    photo_folder,
    process_image,
    save_image,
)
from app.schools.options import SPECIALITIES
from app.schools.uploads import DOC_TYPES, delete_upload, save_upload

MAX_GALLERY = 8

FIELDS = [
    "name",
    "udise_code",
    "board",
    "established_year",
    "address",
    "city",
    "state",
    "pincode",
    "principal_phone",
    "official_email",
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
    if not current_user.is_verified:
        flash("Please verify your email address before registering a school.", "warning")
        return redirect(url_for("main.school_home"))

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
    this_year = datetime.now(timezone.utc).year

    if request.method == "GET":
        form.facilities.data = school.facility_list
        form.specialities.data = school.specialities
        form.admission_open.data = bool(school.admission_open)
        form.admission_deadline.data = school.admission_deadline
        form.admission_url.data = school.admission_url or ""
        form.latitude.data = school.latitude
        form.longitude.data = school.longitude

        saved = {r.year: r for r in school.results}
        years = sorted(saved.keys(), reverse=True)[:3]
        rows = [
            {
                "year": y,
                "class10": float(saved[y].class10_pass) if saved[y].class10_pass is not None else None,
                "class12": float(saved[y].class12_pass) if saved[y].class12_pass is not None else None,
            }
            for y in years
        ]
        while len(rows) < 3:
            rows.append({"year": this_year - len(rows), "class10": None, "class12": None})
        form.results.entries = []
        for r in rows:
            form.results.append_entry(r)

    if form.validate_on_submit():
        for name in (
            "about",
            "medium",
            "fee_min",
            "fee_max",
            "class_from",
            "class_to",
            "student_count",
            "teacher_count",
        ):
            setattr(school, name, getattr(form, name).data)

        school.about = (school.about or "").strip()
        school.website = (form.website.data or "").strip() or None
        school.facilities = ",".join(form.facilities.data or [])

        # Admissions fields
        school.admission_open = bool(form.admission_open.data)
        school.admission_deadline = form.admission_deadline.data
        school.admission_url = (form.admission_url.data or "").strip() or None

        # Location and geocoding
        lat, lng = form.latitude.data, form.longitude.data
        tol = 1e-5
        moved_manually = (
            lat is not None and lng is not None
            and (school.latitude is None
                 or abs(lat - school.latitude) > tol
                 or abs(lng - school.longitude) > tol)
        )
        if form.redetect.data or (school.latitude is None and not moved_manually):
            try:
                from app.schools.geocode import geocode_school
                found = geocode_school(school.address, school.city, school.state, school.pincode)
                if found:
                    school.latitude, school.longitude, school.location_source = found
                    if found[2] == "pincode":
                        flash("Approximate location found from pincode. Drag the pin to adjust if needed.", "info")
            except Exception:
                pass
        elif moved_manually:
            school.latitude, school.longitude, school.location_source = lat, lng, "manual"

        # Sync specialities (SchoolTag kind='speciality')
        wanted_specs = set(form.specialities.data or [])
        for tag in list(school.tags):
            if tag.kind == "speciality":
                if tag.value in wanted_specs:
                    wanted_specs.remove(tag.value)
                else:
                    school.tags.remove(tag)
        for val in sorted(wanted_specs):
            school.tags.append(SchoolTag(school_id=school.id, kind="speciality", value=val))

        # Sync board results (SchoolResult upsert per year)
        wanted_results = {}
        for row in form.results:
            if row.year.data and (row.class10.data is not None or row.class12.data is not None):
                wanted_results[row.year.data] = (row.class10.data, row.class12.data)

        for res in list(school.results):
            if res.year in wanted_results:
                c10, c12 = wanted_results.pop(res.year)
                res.class10_pass = c10
                res.class12_pass = c12
            else:
                school.results.remove(res)
        for year, (c10, c12) in wanted_results.items():
            school.results.append(SchoolResult(school_id=school.id, year=year, class10_pass=c10, class12_pass=c12))

        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("schools.public", school_id=school.id))

    return render_template(
        "schools/profile.html",
        form=form,
        school=school,
        logo_form=LogoForm(),
        gallery_form=GalleryForm(),
        max_gallery=MAX_GALLERY,
    )


@bp.route("/school/profile/logo", methods=["POST"])
@role_required("school")
def upload_logo():
    school = current_user.school
    if school is None or school.status != "approved":
        abort(403)

    form = LogoForm()
    if not form.validate_on_submit():
        flash(next(iter(sum(form.errors.values(), [])), "Choose a logo file."), "danger")
        return redirect(url_for("schools.profile"))

    try:
        data, extension = process_image(form.logo.data, 600, prefer_png=True)
    except ImageError as error:
        flash(str(error), "danger")
        return redirect(url_for("schools.profile"))

    stored = save_image(data, extension)
    old_name = None
    try:
        logo = school.logo
        if logo:
            old_name = logo.stored_name
            logo.stored_name, logo.original_name = stored, form.logo.data.filename[:255]
        else:
            school.photos.append(
                SchoolPhoto(school_id=school.id, kind="logo", stored_name=stored, original_name=form.logo.data.filename[:255])
            )
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_image(stored)
        raise
    if old_name:
        delete_image(old_name)

    flash("Logo updated.", "success")
    return redirect(url_for("schools.profile"))


@bp.route("/school/profile/gallery", methods=["POST"])
@role_required("school")
def upload_gallery():
    school = current_user.school
    if school is None or school.status != "approved":
        abort(403)

    form = GalleryForm()
    files = [f for f in (form.photos.data or []) if f and f.filename]
    if not files:
        flash("Choose at least one photo.", "danger")
        return redirect(url_for("schools.profile"))

    if len(school.gallery) + len(files) > MAX_GALLERY:
        available = max(0, MAX_GALLERY - len(school.gallery))
        flash(f"The gallery can hold up to {MAX_GALLERY} photos. You can add {available} more.", "danger")
        return redirect(url_for("schools.profile"))

    saved = []
    try:
        for storage in files:
            try:
                data, extension = process_image(storage, 1600)
            except ImageError as error:
                raise ImageError(f"{storage.filename}: {error}")
            stored = save_image(data, extension)
            saved.append(stored)
            school.photos.append(
                SchoolPhoto(school_id=school.id, kind="gallery", stored_name=stored, original_name=storage.filename[:255])
            )
        db.session.commit()
    except ImageError as error:
        db.session.rollback()
        for name in saved:
            delete_image(name)
        flash(str(error), "danger")
        return redirect(url_for("schools.profile"))
    except Exception:
        db.session.rollback()
        for name in saved:
            delete_image(name)
        raise

    flash(f"{len(saved)} photo(s) added to gallery.", "success")
    return redirect(url_for("schools.profile"))


@bp.route("/school/profile/photo/<int:photo_id>/delete", methods=["POST"])
@role_required("school")
def delete_photo(photo_id):
    school = current_user.school
    if school is None or school.status != "approved":
        abort(403)

    photo = db.get_or_404(SchoolPhoto, photo_id)
    if photo.school_id != school.id:
        abort(403)

    stored = photo.stored_name
    school.photos.remove(photo)
    db.session.commit()
    delete_image(stored)
    flash("Photo removed.", "info")
    return redirect(url_for("schools.profile"))


def _can_view_school(school):
    if school.is_suspended:
        return current_user.is_authenticated and (
            current_user.role == "admin" or school.owner_id == current_user.id
        )
    if school.status == "approved":
        return True
    return current_user.is_authenticated and (
        current_user.role == "admin" or school.owner_id == current_user.id
    )


@bp.route("/school/photo/<int:photo_id>")
def photo(photo_id):
    photo = db.get_or_404(SchoolPhoto, photo_id)
    if not _can_view_school(photo.school):
        abort(404)
    response = send_from_directory(photo_folder(), photo.stored_name)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@bp.route("/schools")
def listing():
    q = request.args.get("q", "").strip()
    board = request.args.get("board", "").strip()
    max_fee = request.args.get("max_fee", type=int)

    query = db.select(School).filter_by(status="approved", is_suspended=False).order_by(School.name)
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
    if not _can_view_school(school):
        abort(404)

    labels = dict(FACILITIES)
    speciality_labels = dict(SPECIALITIES)
    facilities = [labels[f] for f in school.facility_list if f in labels]
    specialities = [speciality_labels.get(s, s) for s in school.specialities]
    results = sorted(school.results, key=lambda r: r.year, reverse=True)

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
    is_shortlisted = bool(
        current_user.is_authenticated
        and current_user.role == "user"
        and db.session.scalar(
            db.select(UserShortlist).filter_by(user_id=current_user.id, school_id=school.id)
        )
    )
    inquiry_form = InquiryForm()

    return render_template(
        "schools/detail.html",
        school=school,
        facilities=facilities,
        specialities=specialities,
        results=results,
        posts=posts,
        events=events,
        followers=followers,
        following=following,
        is_shortlisted=is_shortlisted,
        inquiry_form=inquiry_form,
    )


def _safe_redirect(fallback_endpoint="schools.connections"):
    target = request.args.get("next") or request.referrer
    if not target or target.startswith("//") or target.startswith("\\\\"):
        return redirect(url_for(fallback_endpoint))
    parsed = urlparse(target)
    if parsed.netloc:
        return redirect(url_for(fallback_endpoint))
    return redirect(target)


@bp.route("/school/connections")
@login_required
def connections():
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    my_school = current_user.school

    active_rows = db.session.scalars(
        db.select(Connection).filter(
            db.or_(Connection.school_low_id == my_school.id, Connection.school_high_id == my_school.id),
            Connection.status == "accepted",
        ).order_by(Connection.responded_at.desc())
    ).all()
    active_conns = []
    for c in active_rows:
        partner = c.receiver if c.requester_school_id == my_school.id else c.requester
        active_conns.append({"connection": c, "school": partner})

    received_rows = db.session.scalars(
        db.select(Connection).filter_by(receiver_school_id=my_school.id, status="pending").order_by(Connection.created_at.desc())
    ).all()

    sent_rows = db.session.scalars(
        db.select(Connection).filter_by(requester_school_id=my_school.id, status="pending").order_by(Connection.created_at.desc())
    ).all()

    related_ids = {my_school.id}
    all_conns = db.session.scalars(
        db.select(Connection).filter(
            db.or_(Connection.school_low_id == my_school.id, Connection.school_high_id == my_school.id),
            Connection.status.in_(["accepted", "pending"])
        )
    ).all()
    for c in all_conns:
        related_ids.add(c.receiver_school_id if c.requester_school_id == my_school.id else c.requester_school_id)

    candidates = db.session.scalars(
        db.select(School).filter(School.status == "approved", School.id.not_in(related_ids))
    ).all()

    suggestions = []
    my_specs = set(my_school.specialities)
    for s in candidates:
        reasons = []
        if s.city and my_school.city and s.city.strip().lower() == my_school.city.strip().lower():
            reasons.append(f"Same city ({s.city})")
        shared = my_specs & set(s.specialities)
        if shared:
            reasons.append(f"Shared specialities ({len(shared)})")
        if my_school.latitude and my_school.longitude and s.latitude and s.longitude:
            dist = haversine_distance(my_school.latitude, my_school.longitude, s.latitude, s.longitude)
            if dist is not None and dist <= 25.0:
                reasons.append(f"{dist} km away")
        if reasons:
            suggestions.append({"school": s, "reasons": reasons})

    suggestions.sort(key=lambda item: len(item["reasons"]), reverse=True)

    return render_template(
        "schools/connections.html",
        active_conns=active_conns,
        received_pending=received_rows,
        sent_pending=sent_rows,
        suggestions=suggestions,
    )


@bp.route("/school/connections/<int:target_school_id>/connect", methods=["POST"])
@login_required
def connect_school(target_school_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    my_school = current_user.school
    if my_school.id == target_school_id:
        flash("You cannot connect with your own school.", "warning")
        return _safe_redirect()

    target = db.get_or_404(School, target_school_id)
    if target.status != "approved":
        abort(404)

    low, high = Connection.pair_ids(my_school.id, target.id)
    conn = db.session.scalar(
        db.select(Connection).filter_by(school_low_id=low, school_high_id=high)
    )

    now = datetime.now(timezone.utc)
    if conn:
        if conn.status == "accepted":
            flash(f"Already connected with {target.name}.", "info")
            return _safe_redirect()
        elif conn.status == "pending":
            flash("A connection request is already pending.", "info")
            return _safe_redirect()
        elif conn.status == "declined":
            if conn.responded_at:
                resp_at = conn.responded_at if conn.responded_at.tzinfo else conn.responded_at.replace(tzinfo=timezone.utc)
                if now - resp_at < timedelta(days=7):
                    days_left = 7 - (now - resp_at).days
                    flash(f"A previous request was declined. You can resend after {days_left} day(s).", "warning")
                    return _safe_redirect()
            conn.requester_school_id = my_school.id
            conn.receiver_school_id = target.id
            conn.status = "pending"
            conn.created_at = now
            conn.responded_at = None
            db.session.commit()
            flash(f"Connection request sent to {target.name}.", "success")
            return _safe_redirect()
        elif conn.status == "cancelled":
            conn.requester_school_id = my_school.id
            conn.receiver_school_id = target.id
            conn.status = "pending"
            conn.created_at = now
            conn.responded_at = None
            db.session.commit()
            flash(f"Connection request sent to {target.name}.", "success")
            return _safe_redirect()
    else:
        conn = Connection(
            requester_school_id=my_school.id,
            receiver_school_id=target.id,
            school_low_id=low,
            school_high_id=high,
            status="pending",
            created_at=now,
        )
        db.session.add(conn)
        db.session.commit()
        flash(f"Connection request sent to {target.name}.", "success")

    return _safe_redirect()


@bp.route("/school/connections/<int:conn_id>/accept", methods=["POST"])
@login_required
def accept_connection(conn_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    conn = db.get_or_404(Connection, conn_id)
    if conn.receiver_school_id != current_user.school.id or conn.status != "pending":
        abort(403)
    conn.status = "accepted"
    conn.responded_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"You are now connected with {conn.requester.name}.", "success")
    return _safe_redirect()


@bp.route("/school/connections/<int:conn_id>/decline", methods=["POST"])
@login_required
def decline_connection(conn_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    conn = db.get_or_404(Connection, conn_id)
    if conn.receiver_school_id != current_user.school.id or conn.status != "pending":
        abort(403)
    conn.status = "declined"
    conn.responded_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(f"Connection request from {conn.requester.name} declined.", "info")
    return _safe_redirect()


@bp.route("/school/connections/<int:conn_id>/cancel", methods=["POST"])
@login_required
def cancel_connection(conn_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    conn = db.get_or_404(Connection, conn_id)
    if conn.requester_school_id != current_user.school.id or conn.status != "pending":
        abort(403)
    conn.status = "cancelled"
    conn.responded_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("Connection request cancelled.", "info")
    return _safe_redirect()


@bp.route("/school/connections/<int:conn_id>/remove", methods=["POST"])
@login_required
def remove_connection(conn_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    conn = db.get_or_404(Connection, conn_id)
    if current_user.school.id not in (conn.school_low_id, conn.school_high_id) or conn.status != "accepted":
        abort(403)
    conn.status = "cancelled"
    conn.responded_at = datetime.now(timezone.utc)
    db.session.commit()
    flash("Connection removed.", "info")
    return _safe_redirect()


@bp.route("/schools/nearby")
def nearby():
    q = (request.args.get("q") or "").strip()
    radius = request.args.get("radius", default=10, type=int)
    if radius not in (2, 5, 10, 20):
        radius = 10

    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    center = None
    if lat is not None and lng is not None:
        center = (lat, lng)
    elif q:
        if q.isdigit() and len(q) == 6:
            coords = geocode_pincode(q)
            if coords:
                center = coords
        if not center:
            matching_school = db.session.scalar(
                db.select(School).filter(
                    School.status == "approved",
                    School.latitude.is_not(None),
                    db.or_(
                        School.city.ilike(f"%{q}%"),
                        School.pincode == q,
                        School.address.ilike(f"%{q}%"),
                        School.name.ilike(f"%{q}%"),
                    ),
                ).limit(1)
            )
            if matching_school:
                center = (matching_school.latitude, matching_school.longitude)
        if not center:
            from app.schools.geocode import geocode_place
            center = geocode_place(q)

    schools_with_coords = db.session.scalars(
        db.select(School).filter(
            School.status == "approved",
            School.latitude.is_not(None),
            School.longitude.is_not(None),
        )
    ).all()

    results = []
    if center:
        c_lat, c_lng = center
        for s in schools_with_coords:
            dist = haversine_distance(c_lat, c_lng, s.latitude, s.longitude)
            if dist is not None and dist <= radius:
                results.append({"school": s, "distance": dist})
        results.sort(key=lambda x: x["distance"])
    else:
        if schools_with_coords:
            center = (schools_with_coords[0].latitude, schools_with_coords[0].longitude)
            for s in schools_with_coords:
                results.append({"school": s, "distance": None})

    without_coords = db.session.scalars(
        db.select(School).filter(
            School.status == "approved",
            db.or_(School.latitude.is_(None), School.longitude.is_(None)),
        ).order_by(School.name)
    ).all()

    return render_template(
        "schools/nearby.html",
        results=results,
        without_coords=without_coords,
        center=center,
        radius=radius,
        q=q,
    )


@bp.route("/schools/<int:school_id>/inquire", methods=["POST"])
@login_required
def inquire(school_id):
    if current_user.role != "user":
        abort(403)
    school = db.get_or_404(School, school_id)
    if school.status != "approved" or school.is_suspended:
        abort(404)

    form = InquiryForm()
    if form.validate_on_submit():
        inquiry = AdmissionInquiry(
            user_id=current_user.id,
            school_id=school.id,
            child_class=form.child_class.data,
            message=form.message.data.strip(),
            status="new",
        )
        db.session.add(inquiry)
        db.session.commit()
        flash("Your admission inquiry has been submitted to the school administration.", "success")
    else:
        for err_list in form.errors.values():
            for err in err_list:
                flash(err, "warning")
    return redirect(url_for("schools.public", school_id=school.id))


@bp.route("/school/inquiries")
@login_required
def inquiries():
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    school = current_user.school
    items = db.session.scalars(
        db.select(AdmissionInquiry).filter_by(school_id=school.id).order_by(AdmissionInquiry.created_at.desc())
    ).all()
    reply_form = InquiryReplyForm()
    return render_template("schools/inquiries.html", inquiries=items, form=reply_form)


@bp.route("/school/inquiries/<int:inquiry_id>/reply", methods=["POST"])
@login_required
def reply_inquiry(inquiry_id):
    if current_user.role != "school" or not current_user.school or current_user.school.status != "approved":
        abort(403)
    inquiry = db.get_or_404(AdmissionInquiry, inquiry_id)
    if inquiry.school_id != current_user.school.id:
        abort(403)

    form = InquiryReplyForm()
    if form.validate_on_submit():
        inquiry.reply = form.reply.data.strip()
        inquiry.status = "replied"
        inquiry.replied_at = datetime.now(timezone.utc)
        db.session.commit()
        flash(f"Reply sent to {inquiry.user.name}.", "success")
    else:
        for err_list in form.errors.values():
            for err in err_list:
                flash(err, "warning")
    return redirect(url_for("schools.inquiries"))
