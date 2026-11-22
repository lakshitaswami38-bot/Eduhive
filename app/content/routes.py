from datetime import datetime

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import db
from app.content import bp
from app.content.forms import EventForm, EventRegisterForm, PostForm
from app.decorators import role_required
from app.models import Event, EventRegistration, Post, PostLike
from app.schools.images import ImageError, delete_image, process_image, save_image


def _approved_school():
    school = current_user.school
    if school is None or school.status != "approved":
        return None
    return school


def _can_manage(school):
    return current_user.role == "admin" or (school and school.owner_id == current_user.id)


def _safe_next(default_endpoint="content.events"):
    target = request.args.get("next") or request.referrer or url_for(default_endpoint)
    if not target.startswith("/") or target.startswith("//") or "\\" in target:
        target = url_for(default_endpoint)
    return target


def _safe_redirect_post(school_id):
    target = request.args.get("next") or request.referrer
    if not target or target.startswith("//") or target.startswith("\\\\") or "\\" in target:
        return redirect(url_for("schools.public", school_id=school_id))
    from urllib.parse import urlparse
    parsed = urlparse(target)
    if parsed.netloc:
        return redirect(url_for("schools.public", school_id=school_id))
    return redirect(target)


@bp.route("/school/posts/new", methods=["GET", "POST"])
@role_required("school")
def new_post():
    school = _approved_school()
    if school is None:
        flash("You can post after your school is approved.", "info")
        return redirect(url_for("schools.status"))

    form = PostForm()
    if form.validate_on_submit():
        photo_name = None
        if form.photo.data and form.photo.data.filename:
            try:
                data, ext = process_image(form.photo.data, 1600)
                photo_name = save_image(data, ext)
            except ImageError as err:
                flash(str(err), "danger")
                return render_template("content/form.html", form=form, heading="New post")
            except Exception:
                flash("Could not process the uploaded photo.", "danger")
                return render_template("content/form.html", form=form, heading="New post")

        post = Post(
            school_id=school.id,
            title=form.title.data.strip(),
            body=form.body.data.strip(),
            photo_name=photo_name,
        )
        db.session.add(post)
        db.session.commit()
        flash("Post published.", "success")
        return redirect(url_for("schools.public", school_id=school.id))
    return render_template("content/form.html", form=form, heading="New post")


@bp.route("/posts/<int:post_id>/delete", methods=["POST"])
@login_required
def delete_post(post_id):
    post = db.get_or_404(Post, post_id)
    if not _can_manage(post.school):
        abort(403)
    school_id = post.school_id
    if post.photo_name:
        delete_image(post.photo_name)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted.", "info")
    return _safe_redirect_post(school_id)


@bp.route("/posts/<int:post_id>/like", methods=["POST"])
@login_required
def toggle_like(post_id):
    # Admin cannot like
    if current_user.role == "admin":
        abort(403)

    # Pending or rejected schools cannot like
    if current_user.role == "school":
        if not current_user.school or current_user.school.status != "approved":
            abort(403)

    post = db.get_or_404(Post, post_id)
    # Pending or rejected schools cannot be liked
    if post.school.status != "approved":
        abort(404)

    existing = db.session.scalar(
        db.select(PostLike).filter_by(post_id=post.id, user_id=current_user.id)
    )
    if existing:
        db.session.delete(existing)
        flash("Post unliked.", "info")
    else:
        db.session.add(PostLike(post_id=post.id, user_id=current_user.id))
        flash("Post liked.", "success")

    db.session.commit()
    return _safe_redirect_post(post.school_id)


@bp.route("/posts/<int:post_id>/photo")
def post_photo(post_id):
    post = db.get_or_404(Post, post_id)
    if not post.photo_name:
        abort(404)
    school = post.school
    is_allowed = (school.status == "approved") or (
        current_user.is_authenticated and (current_user.role == "admin" or school.owner_id == current_user.id)
    )
    if not is_allowed:
        abort(404)
    from flask import send_from_directory
    from app.schools.images import photo_folder
    response = send_from_directory(photo_folder(), post.photo_name)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "public, max-age=86400"
    return response


@bp.route("/school/events/new", methods=["GET", "POST"])
@role_required("school")
def new_event():
    school = _approved_school()
    if school is None:
        flash("You can create events after your school is approved.", "info")
        return redirect(url_for("schools.status"))

    form = EventForm()
    if form.validate_on_submit():
        db.session.add(
            Event(
                school_id=school.id,
                title=form.title.data.strip(),
                description=form.description.data.strip(),
                venue=form.venue.data.strip(),
                starts_at=form.starts_at.data,
                capacity=form.capacity.data,
            )
        )
        db.session.commit()
        flash("Event published.", "success")
        return redirect(url_for("schools.public", school_id=school.id))
    return render_template("content/form.html", form=form, heading="New event")


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

    user_reg = _registration(event.id)
    is_organizer = current_user.is_authenticated and _can_manage(event.school)

    # Can current user register?
    can_register = False
    if current_user.is_authenticated:
        if current_user.role == "user":
            can_register = True
        elif current_user.role == "school":
            # Approved schools can register for other schools' events, but not their own
            if current_user.school and current_user.school.status == "approved" and current_user.school.id != event.school_id:
                can_register = True

    form = EventRegisterForm()
    return render_template(
        "content/event_detail.html",
        event=event,
        joined=user_reg is not None,
        registration=user_reg,
        can_register=can_register,
        is_organizer=is_organizer,
        form=form,
    )


@bp.route("/events/<int:event_id>/join", methods=["POST"])
@login_required
def join(event_id):
    event = db.get_or_404(Event, event_id)
    if event.school.status != "approved":
        abort(404)
    if event.is_past:
        flash("This event has already happened.", "warning")
        return redirect(url_for("content.event_detail", event_id=event.id))

    # Check who is registering
    school_id = None
    if current_user.role == "admin":
        abort(403)
    elif current_user.role == "school":
        if not current_user.school or current_user.school.status != "approved":
            abort(403)
        if current_user.school.id == event.school_id:
            flash("You cannot register for your own school's event.", "warning")
            return redirect(url_for("content.event_detail", event_id=event.id))
        school_id = current_user.school.id
    elif current_user.role != "user":
        abort(403)

    if _registration(event.id):
        flash("You are already registered for this event.", "info")
        return redirect(url_for("content.event_detail", event_id=event.id))

    form = EventRegisterForm()
    participants = 1
    note = None
    if form.validate_on_submit():
        participants = form.participants.data or 1
        note = (form.note.data or "").strip() or None

    if event.spots_left is not None:
        if event.spots_left <= 0:
            flash("Sorry, this event is full.", "warning")
            return redirect(url_for("content.event_detail", event_id=event.id))
        if participants > event.spots_left:
            flash(f"Only {event.spots_left} spot(s) remaining.", "warning")
            return redirect(url_for("content.event_detail", event_id=event.id))

    try:
        reg = EventRegistration(
            event_id=event.id,
            user_id=current_user.id,
            school_id=school_id,
            participants=participants,
            note=note,
        )
        db.session.add(reg)
        db.session.commit()
        flash("You have joined this event.", "success")
    except IntegrityError:
        db.session.rollback()
        flash("You are already registered for this event.", "info")

    return redirect(url_for("content.event_detail", event_id=event.id))


@bp.route("/events/<int:event_id>/leave", methods=["POST"])
@login_required
def leave(event_id):
    event = db.get_or_404(Event, event_id)
    if event.is_past:
        flash("Cannot cancel registration for an event that has already occurred.", "warning")
        return redirect(url_for("content.event_detail", event_id=event.id))

    reg = _registration(event_id)
    if reg:
        db.session.delete(reg)
        db.session.commit()
        flash("Your registration has been cancelled.", "info")
    return redirect(url_for("content.event_detail", event_id=event_id))


@bp.route("/events/<int:event_id>/registrations")
@login_required
def registrations(event_id):
    event = db.get_or_404(Event, event_id)
    if not _can_manage(event.school):
        abort(403)

    regs = db.session.scalars(
        db.select(EventRegistration).filter_by(event_id=event.id).order_by(EventRegistration.created_at.desc())
    ).all()
    total_attendees = sum(r.participants for r in regs)
    return render_template(
        "content/registrations.html",
        event=event,
        registrations=regs,
        total_attendees=total_attendees,
    )
