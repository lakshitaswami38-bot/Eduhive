from datetime import datetime

from flask import abort, flash, redirect, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.content import bp
from app.content.forms import EventForm, PostForm
from app.decorators import role_required
from app.models import Event, EventRegistration, Post


def _approved_school():
    school = current_user.school
    if school is None or school.status != "approved":
        return None
    return school


def _can_manage(school):
    return current_user.role == "admin" or school.owner_id == current_user.id


@bp.route("/school/posts/new", methods=["GET", "POST"])
@role_required("school")
def new_post():
    school = _approved_school()
    if school is None:
        flash("You can post after your school is approved.", "info")
        return redirect(url_for("schools.status"))

    form = PostForm()
    if form.validate_on_submit():
        db.session.add(Post(school_id=school.id, title=form.title.data.strip(), body=form.body.data.strip()))
        db.session.commit()
        flash("Post published.", "success")
        return redirect(url_for("schools.public", school_id=school.id))
    return render_template("content/form.html", form=form, heading="New post")


@bp.route("/school/events/new", methods=["GET", "POST"])
@role_required("school")
def new_event():
    school = _approved_school()
    if school is None:
        flash("You can create events after your school is approved.", "info")
        return redirect(url_for("schools.status"))

    form = EventForm()
    if form.validate_on_submit():
        db.session.add(Event(
            school_id=school.id,
            title=form.title.data.strip(),
            description=form.description.data.strip(),
            venue=form.venue.data.strip(),
            starts_at=form.starts_at.data,
            capacity=form.capacity.data,
        ))
        db.session.commit()
        flash("Event published.", "success")
        return redirect(url_for("schools.public", school_id=school.id))
    return render_template("content/form.html", form=form, heading="New event")


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if not _can_manage(post.school):
        abort(403)
    school_id = post.school_id
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return redirect(url_for("schools.public", school_id=school_id))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id):
    event = db.get_or_404(Event, event_id)
    if not _can_manage(event.school):
        abort(403)
    school_id = event.school_id
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted.", "info")
    return redirect(url_for("schools.public", school_id=school_id))


@bp.route("/events")
def events():
    upcoming = db.session.scalars(
        db.select(Event).filter(Event.starts_at >= datetime.now()).order_by(Event.starts_at)
    ).all()
    upcoming = [e for e in upcoming if e.school.status == "approved"]
    return render_template("content/events.html", events=upcoming)


def _registration(event_id):
    if not current_user.is_authenticated:
        return None
    return db.session.scalar(
        db.select(EventRegistration).filter_by(event_id=event_id, user_id=current_user.id)
    )


@bp.route("/events/<int:event_id>")
def event_detail(event_id):
    event = db.get_or_404(Event, event_id)
    if event.school.status != "approved":
        abort(404)
    return render_template("content/event_detail.html", event=event, joined=_registration(event.id) is not None)


@bp.route("/events/<int:event_id>/join", methods=["POST"])
@role_required("user")
def join(event_id):
    event = db.get_or_404(Event, event_id)
    if event.school.status != "approved":
        abort(404)
    if event.is_past:
        flash("This event has already happened.", "warning")
    elif _registration(event.id):
        flash("You have already joined this event.", "info")
    elif event.spots_left == 0:
        flash("Sorry, this event is full.", "warning")
    else:
        try:
            db.session.add(EventRegistration(event_id=event.id, user_id=current_user.id))
            db.session.commit()
            flash("You have joined this event.", "success")
        except IntegrityError:
            db.session.rollback()
            flash("You have already joined this event.", "info")
    return redirect(url_for("content.event_detail", event_id=event.id))


@bp.route("/events/<int:event_id>/leave", methods=["POST"])
@role_required("user")
def leave(event_id):
    reg = _registration(event_id)
    if reg:
        db.session.delete(reg)
        db.session.commit()
        flash("You have left this event.", "info")
    return redirect(url_for("content.event_detail", event_id=event_id))