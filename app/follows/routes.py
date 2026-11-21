from datetime import datetime

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user
from sqlalchemy.exc import IntegrityError

from app import db
from app.decorators import role_required
from app.follows import bp
from app.models import Event, Follow, Post, School


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
@role_required("user")
def feed():
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

    return render_template("follows/feed.html", items=items, schools=schools)