from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app import db
from app.decorators import role_required
from app.matches import bp
from app.matches.forms import PriorityForm
from app.matches.scoring import rank_schools
from app.models import UserPriority


@bp.route("/priorities", methods=["GET", "POST"])
@role_required("user")
def priorities():
    p = current_user.priority
    form = PriorityForm(obj=p)
    if request.method == "GET" and p:
        form.facilities.data = p.facility_list

    if form.validate_on_submit():
        if p is None:
            p = UserPriority(user_id=current_user.id)
            db.session.add(p)
        p.max_fee = form.max_fee.data
        p.board = form.board.data or None
        p.city = (form.city.data or "").strip() or None
        p.class_needed = form.class_needed.data
        p.facilities = ",".join(form.facilities.data)
        p.w_fee = form.w_fee.data
        p.w_board = form.w_board.data
        p.w_city = form.w_city.data
        p.w_facilities = form.w_facilities.data
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
    has_criteria = any([p.max_fee, p.board, p.city, p.facility_list])
    results = rank_schools(p) if has_criteria else []
    return render_template("matches/list.html", results=results, has_criteria=has_criteria)