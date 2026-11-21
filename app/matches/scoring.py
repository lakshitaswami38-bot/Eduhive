from app import db
from app.models import School
from app.schools.forms import FACILITIES

FAC_LABELS = dict(FACILITIES)


def score_school(school, p):
    """Return (score 0-100, reasons). Only criteria the user filled in are counted."""
    parts = []  # (weight, fraction 0-1, ok_text_or_miss_text, matched?)

    if p.max_fee:
        if school.fee_min <= p.max_fee:
            frac, ok = 1.0, True
            text = f"Fee from Rs. {school.fee_min:,} fits your budget"
        else:
            over = (school.fee_min - p.max_fee) / p.max_fee
            frac, ok = max(0.0, 1.0 - over), False
            text = f"Fee from Rs. {school.fee_min:,} is above your budget"
        parts.append((p.w_fee, frac, text, ok))

    if p.board:
        ok = school.board == p.board
        text = f"Board: {school.board}" + ("" if ok else f" (you wanted {p.board})")
        parts.append((p.w_board, 1.0 if ok else 0.0, text, ok))

    if p.city:
        ok = school.city.strip().lower() == p.city.strip().lower()
        text = f"City: {school.city}" + ("" if ok else f" (you wanted {p.city})")
        parts.append((p.w_city, 1.0 if ok else 0.0, text, ok))

    wanted = set(p.facility_list)
    if wanted:
        have = set(school.facility_list)
        hit = wanted & have
        missing = [FAC_LABELS.get(f, f) for f in sorted(wanted - have)]
        text = f"Facilities: {len(hit)} of {len(wanted)} you wanted"
        if missing:
            text += " (missing: " + ", ".join(missing) + ")"
        parts.append((p.w_facilities, len(hit) / len(wanted), text, not missing))

    if not parts:
        return 0, []

    total = sum(w for w, _f, _t, _o in parts)
    score = round(100 * sum(w * f for w, f, _t, _o in parts) / total)
    return score, [(text, ok) for _w, _f, text, ok in parts]


def rank_schools(p):
    query = db.select(School).filter(School.status == "approved", School.fee_min.is_not(None))
    if p.class_needed:
        query = query.filter(School.class_from <= p.class_needed, School.class_to >= p.class_needed)

    results = []
    for school in db.session.scalars(query).all():
        score, reasons = score_school(school, p)
        results.append({"school": school, "score": score, "reasons": reasons})
    results.sort(key=lambda r: (-r["score"], r["school"].name))
    return results