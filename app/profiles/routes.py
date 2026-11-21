"""
Legacy profile routes (older design with separate profiles blueprint).
Commented out to prevent BuildError and maintain a clean url_for audit.
The active school profile management lives in app/schools/routes.py.

from datetime import datetime, timezone

from flask import abort, flash, redirect, render_template, send_from_directory, url_for
from flask_login import current_user

from app import db
from app.decorators import role_required
from app.models import School, SchoolPhoto, SchoolProfile, SchoolResult, SchoolTag
from app.profiles import bp, geocode
from app.profiles.forms import GalleryForm, LogoForm, SchoolProfileForm
from app.profiles.images import ImageError, delete_image, photo_folder, process_image, save_image
from app.profiles.options import FACILITY_LABELS, SPECIALITY_LABELS

MAX_GALLERY = 8
LOCATION_TOLERANCE = 1e-5  # about 1 metre


def _approved_school():
    school = current_user.school
    if school is None:
        return None, redirect(url_for("schools.register"))
    if school.status != "approved":
        flash("You can edit your profile after an admin approves your school.", "info")
        return None, redirect(url_for("schools.status"))
    return school, None


def _address_key(school):
    return "|".join([school.address, school.city, school.state, school.pincode]).lower()


def _defaults(school):
    profile = school.profile
    this_year = datetime.now(timezone.utc).year
    saved = {r.year: r for r in school.results}
    years = sorted(saved, reverse=True)[:3]
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

    data = {
        "facilities": school.facilities,
        "specialities": school.specialities,
        "results": rows,
    }
    if profile:
        for field in ("tagline", "about", "medium", "classes_from", "classes_to", "total_students",
                      "fee_min", "fee_max", "admission_open", "admission_deadline", "admission_url",
                      "latitude", "longitude"):
            data[field] = getattr(profile, field)
    return data


def _sync_tags(school, kind, wanted):
    wanted = set(wanted)
    for tag in [t for t in school.tags if t.kind == kind]:
        if tag.value in wanted:
            wanted.discard(tag.value)
        else:
            school.tags.remove(tag)
    for value in sorted(wanted):
        school.tags.append(SchoolTag(kind=kind, value=value))


def _sync_results(school, form):
    wanted = {}
    for row in form.results:
        if row.class10.data is not None or row.class12.data is not None:
            wanted[row.year.data] = (row.class10.data, row.class12.data)
    for result in list(school.results):
        if result.year in wanted:
            result.class10_pass, result.class12_pass = wanted.pop(result.year)
        else:
            school.results.remove(result)
    for year, (c10, c12) in wanted.items():
        school.results.append(SchoolResult(year=year, class10_pass=c10, class12_pass=c12))


def _update_location(school, profile, form):
    lat, lng = form.latitude.data, form.longitude.data
    moved_by_user = (
        lat is not None and lng is not None
        and (profile.latitude is None
             or abs(lat - profile.latitude) > LOCATION_TOLERANCE
             or abs(lng - profile.longitude) > LOCATION_TOLERANCE)
    )
    if moved_by_user:
        profile.latitude, profile.longitude, profile.location_source = lat, lng, "manual"
        return

    if form.redetect.data or profile.latitude is None:
        found = geocode.geocode_school(school.address, school.city, school.state, school.pincode)
        if found:
            profile.latitude, profile.longitude, profile.location_source = found
            profile.geocode_key = _address_key(school)
            if found[2] == "pincode":
                flash("We could only find your pincode area. Drag the pin to your school gate for an exact spot.", "warning")
        else:
            flash("We could not find your address on the map. Click on the map to place the pin yourself.", "warning")


@bp.route("/school/profile/edit", methods=["GET", "POST"])
@role_required("school")
def edit():
    school, early = _approved_school()
    if early:
        return early

    form = SchoolProfileForm(data=_defaults(school))
    if form.validate_on_submit():
        profile = school.profile
        if profile is None:
            profile = SchoolProfile(school=school)
            db.session.add(profile)

        profile.tagline = (form.tagline.data or "").strip() or None
        profile.about = (form.about.data or "").strip() or None
        profile.medium = form.medium.data or None
        profile.classes_from = form.classes_from.data or None
        profile.classes_to = form.classes_to.data or None
        profile.total_students = form.total_students.data
        profile.fee_min = form.fee_min.data
        profile.fee_max = form.fee_max.data
        profile.admission_open = bool(form.admission_open.data)
        profile.admission_deadline = form.admission_deadline.data
        profile.admission_url = (form.admission_url.data or "").strip() or None

        _sync_tags(school, "facility", form.facilities.data)
        _sync_tags(school, "speciality", form.specialities.data)
        _sync_results(school, form)
        _update_location(school, profile, form)

        db.session.commit()
        flash("Profile saved.", "success")
        return redirect(url_for("profiles.edit"))

    return render_template(
        "profiles/edit.html", form=form, school=school,
        logo_form=LogoForm(), gallery_form=GalleryForm(), max_gallery=MAX_GALLERY,
    )


@bp.route("/school/profile/logo", methods=["POST"])
@role_required("school")
def upload_logo():
    school, early = _approved_school()
    if early:
        return early
    form = LogoForm()
    if not form.validate_on_submit():
        flash(next(iter(sum(form.errors.values(), [])), "Choose a logo file."), "danger")
        return redirect(url_for("profiles.edit"))

    try:
        data, extension = process_image(form.logo.data, 600, prefer_png=True)
    except ImageError as error:
        flash(str(error), "danger")
        return redirect(url_for("profiles.edit"))

    stored = save_image(data, extension)
    old_name = None
    try:
        logo = school.logo
        if logo:
            old_name = logo.stored_name
            logo.stored_name, logo.original_name = stored, form.logo.data.filename[:255]
        else:
            school.photos.append(SchoolPhoto(kind="logo", stored_name=stored, original_name=form.logo.data.filename[:255]))
        db.session.commit()
    except Exception:
        db.session.rollback()
        delete_image(stored)
        raise
    if old_name:
        delete_image(old_name)
    flash("Logo updated.", "success")
    return redirect(url_for("profiles.edit"))


@bp.route("/school/profile/gallery", methods=["POST"])
@role_required("school")
def upload_gallery():
    school, early = _approved_school()
    if early:
        return early
    form = GalleryForm()
    files = [f for f in (form.photos.data or []) if f and f.filename]
    if not files:
        flash("Choose at least one photo.", "danger")
        return redirect(url_for("profiles.edit"))
    if len(school.gallery) + len(files) > MAX_GALLERY:
        flash(f"The gallery can hold {MAX_GALLERY} photos. You can add {MAX_GALLERY - len(school.gallery)} more.", "danger")
        return redirect(url_for("profiles.edit"))

    saved = []
    try:
        for storage in files:
            try:
                data, extension = process_image(storage, 1600)
            except ImageError as error:
                raise ImageError(f"{storage.filename}: {error}")
            stored = save_image(data, extension)
            saved.append(stored)
            school.photos.append(SchoolPhoto(kind="gallery", stored_name=stored, original_name=storage.filename[:255]))
        db.session.commit()
    except ImageError as error:
        db.session.rollback()
        for name in saved:
            delete_image(name)
        flash(str(error), "danger")
        return redirect(url_for("profiles.edit"))
    except Exception:
        db.session.rollback()
        for name in saved:
            delete_image(name)
        raise
    flash(f"{len(saved)} photo(s) added.", "success")
    return redirect(url_for("profiles.edit"))


@bp.route("/school/profile/photo/<int:photo_id>/delete", methods=["POST"])
@role_required("school")
def delete_photo(photo_id):
    school, early = _approved_school()
    if early:
        return early
    photo = db.get_or_404(SchoolPhoto, photo_id)
    if photo.school_id != school.id:
        abort(403)
    stored = photo.stored_name
    school.photos.remove(photo)
    db.session.commit()
    delete_image(stored)
    flash("Photo removed.", "info")
    return redirect(url_for("profiles.edit"))


def _can_view(school):
    if school.status == "approved":
        return True
    return current_user.is_authenticated and (
        current_user.role == "admin" or school.owner_id == current_user.id
    )


@bp.route("/school/photo/<int:photo_id>")
def photo(photo_id):
    photo = db.get_or_404(SchoolPhoto, photo_id)
    if not _can_view(photo.school):
        abort(404)
    response = send_from_directory(photo_folder(), photo.stored_name)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@bp.route("/school/<int:school_id>")
def public(school_id):
    school = db.get_or_404(School, school_id)
    if not _can_view(school):
        abort(404)
    return render_template(
        "profiles/public.html", school=school, profile=school.profile,
        facility_labels=FACILITY_LABELS, speciality_labels=SPECIALITY_LABELS,
        results=sorted(school.results, key=lambda r: r.year, reverse=True),
        is_preview=school.status != "approved",
    )
"""
