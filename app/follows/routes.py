from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.decorators import role_required
from app.follows import bp
from app.models import Connection, Event, Follow, Post, School


def _find(school_id):
    return db.session.scalar(
        db.select(Follow).filter_by(user_id=current_user.id, school_id=school_id)
    )


@bp.route("/schools/<int:school_id>/follow", methods=["POST"])
@role_required("user")
def follow(school_id):
    school = db.get_or_404(School, school_id)
    if school.status != "approved":
        abort(404)
    if _find(school.id):
        flash("You already follow this school.", "info")
    else:
        try:
            db.session.add(Follow(user_id=current_user.id, school_id=school.id))
            db.session.commit()
            flash(f"You now follow {school.name}.", "success")
        except IntegrityError:
            db.session.rollback()
    return redirect(url_for("schools.public", school_id=school.id))


@bp.route("/schools/<int:school_id>/unfollow", methods=["POST"])
@role_required("user")
def unfollow(school_id):
    row = _find(school_id)
    if row:
        db.session.delete(row)
        db.session.commit()
        flash("You unfollowed this school.", "info")
    return redirect(url_for("schools.public", school_id=school_id))


@bp.route("/feed")
@role_required("user", "school")
def feed():
    tab = request.args.get("tab", "following")
    schools = []
    ids = []

    if tab == "network" and current_user.role == "school" and current_user.school:
        my_school = current_user.school
        conns = db.session.scalars(
            db.select(Connection).filter(
                db.or_(Connection.school_low_id == my_school.id, Connection.school_high_id == my_school.id),
                Connection.status == "accepted",
            )
        ).all()
        connected_ids = [
            c.receiver_school_id if c.requester_school_id == my_school.id else c.requester_school_id
            for c in conns
        ]
        if connected_ids:
            schools = db.session.scalars(
                db.select(School).filter(School.id.in_(connected_ids), School.status == "approved")
            ).all()
            ids = [s.id for s in schools]
    else:
        tab = "following"
        follows = db.session.scalars(
            db.select(Follow).filter_by(user_id=current_user.id).order_by(Follow.created_at.desc())
        ).all()
        schools = [f.school for f in follows if f.school.status == "approved"]
        ids = [s.id for s in schools]

    items = []
    if ids:
        posts = db.session.scalars(
            db.select(Post).filter(Post.school_id.in_(ids)).order_by(Post.created_at.desc()).limit(30)
        ).all()
        events = db.session.scalars(
            db.select(Event)
            .filter(Event.school_id.in_(ids), Event.starts_at >= datetime.now())
            .order_by(Event.starts_at)
            .limit(30)
        ).all()
        items = [{"kind": "post", "obj": p, "when": p.created_at} for p in posts]
        items += [{"kind": "event", "obj": e, "when": e.created_at} for e in events]
        items.sort(key=lambda i: i["when"], reverse=True)

    return render_template("follows/feed.html", items=items, schools=schools, tab=tab)