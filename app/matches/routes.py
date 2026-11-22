from urllib.parse import urlparse

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func

from app import db
from app.decorators import role_required
from app.matches import bp
from app.matches.forms import PriorityForm
from app.matches.scoring import rank_schools
from app.models import School, UserPriority, UserShortlist
from app.schools.forms import FACILITIES
from app.schools.geocode import geocode_pincode
from app.schools.options import SPECIALITIES

FAC_LABELS = dict(FACILITIES)
SPEC_LABELS = dict(SPECIALITIES)


def _safe_redirect(fallback="matches.ranked"):
    target = request.args.get("next") or request.referrer
    if not target or target.startswith("//") or target.startswith("\\\\"):
        return redirect(url_for(fallback))
    parsed = urlparse(target)
    if parsed.netloc:
        return redirect(url_for(fallback))
    return redirect(target)


@bp.route("/priorities", methods=["GET", "POST"])
@role_required("user")
def priorities():
    p = current_user.priority
    form = PriorityForm(obj=p)
    if request.method == "GET" and p:
        form.facilities.data = p.facility_list
        form.specialities.data = p.speciality_list
        form.admission_only.data = p.admission_only

    if form.validate_on_submit():
        if p is None:
            p = UserPriority(user_id=current_user.id)
            db.session.add(p)
        p.max_fee = form.max_fee.data
        p.board = form.board.data or None
        p.city = (form.city.data or "").strip() or None
        p.class_needed = form.class_needed.data
        p.facilities = ",".join(form.facilities.data)
        p.specialities = ",".join(form.specialities.data)
        p.admission_only = bool(form.admission_only.data)
        p.max_distance = form.max_distance.data

        # Geocode pincode or use browser coords
        lat_val = form.latitude.data
        lng_val = form.longitude.data
        if lat_val and lng_val:
            try:
                p.latitude = float(lat_val)
                p.longitude = float(lng_val)
            except ValueError:
                pass
        elif form.pincode.data and form.pincode.data.strip():
            coords = geocode_pincode(form.pincode.data.strip())
            if coords:
                p.latitude, p.longitude = coords

        p.w_fee = form.w_fee.data
        p.w_board = form.w_board.data
        p.w_city = form.w_city.data
        p.w_facilities = form.w_facilities.data
        p.w_specialities = form.w_specialities.data
        p.w_results = form.w_results.data
        p.w_distance = form.w_distance.data
        db.session.commit()
        flash("Priorities saved.", "success")
        return redirect(url_for("matches.ranked"))
    return render_template("matches/priorities.html", form=form)


@bp.route("/matches")
@role_required("user")
def ranked():
    p = current_user.priority
    if p is None:
        flash("Tell us what matters to you first.", "info")
        return redirect(url_for("matches.priorities"))
    has_criteria = any([
        p.max_fee,
        p.board,
        p.city,
        p.facility_list,
        p.speciality_list,
        p.class_needed,
        p.admission_only,
        p.max_distance,
    ])
    results = rank_schools(p) if has_criteria else []

    weights = {
        "fee": p.w_fee,
        "board": p.w_board,
        "city": p.w_city,
        "facilities": p.w_facilities,
        "specialities": p.w_specialities,
        "results": p.w_results,
        "distance": p.w_distance,
    }

    return render_template(
        "matches/list.html",
        results=results,
        has_criteria=has_criteria,
        priority=p,
        weights=weights,
    )


@bp.route("/schools/<int:school_id>/shortlist", methods=["POST"])
@role_required("user")
def toggle_shortlist(school_id):
    school = db.get_or_404(School, school_id)
    if school.status != "approved" or school.is_suspended:
        abort(404)

    existing = db.session.scalar(
        db.select(UserShortlist).filter_by(user_id=current_user.id, school_id=school.id)
    )
    if existing:
        db.session.delete(existing)
        db.session.commit()
        flash(f"{school.name} removed from your shortlist.", "info")
    else:
        count = db.session.scalar(
            db.select(func.count()).select_from(UserShortlist).filter_by(user_id=current_user.id)
        )
        if count >= 20:
            flash("Shortlist limit reached (maximum 20 schools).", "warning")
        else:
            sl = UserShortlist(user_id=current_user.id, school_id=school.id)
            db.session.add(sl)
            db.session.commit()
            flash(f"{school.name} added to your shortlist.", "success")

    return _safe_redirect("matches.shortlist")


@bp.route("/shortlist")
@role_required("user")
def shortlist():
    shortlists = db.session.scalars(
        db.select(UserShortlist).filter_by(user_id=current_user.id).order_by(UserShortlist.created_at.desc())
    ).all()
    schools = [sl.school for sl in shortlists if sl.school.status == "approved" and not sl.school.is_suspended]
    return render_template("matches/shortlist.html", schools=schools)


@bp.route("/compare")
def compare():
    raw_ids = request.args.getlist("id", type=int)
    if not raw_ids and request.args.get("ids"):
        try:
            raw_ids = [int(x.strip()) for x in request.args.get("ids").split(",") if x.strip()]
        except ValueError:
            raw_ids = []

    # Filter distinct valid IDs preserving order
    school_ids = []
    for sid in raw_ids:
        if sid not in school_ids:
            school_ids.append(sid)

    if len(school_ids) < 2 or len(school_ids) > 3:
        flash("Please select 2 or 3 schools to compare side by side.", "warning")
        if current_user.is_authenticated and current_user.role == "user":
            return redirect(url_for("matches.shortlist"))
        return redirect(url_for("schools.listing"))

    schools = []
    for sid in school_ids:
        s = db.session.scalar(
            db.select(School).filter_by(id=sid, status="approved", is_suspended=False)
        )
        if s:
            schools.append(s)

    if len(schools) < 2:
        flash("Could not find enough verified schools to compare.", "warning")
        return redirect(url_for("schools.listing"))

    # Prepare structured comparison matrix
    fac_labels = FAC_LABELS
    spec_labels = SPEC_LABELS

    return render_template(
        "matches/compare.html",
        schools=schools,
        fac_labels=fac_labels,
        spec_labels=spec_labels,
    )
