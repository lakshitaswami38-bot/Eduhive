from app import db
from app.models import School
from app.schools.forms import FACILITIES
from app.schools.geocode import haversine_distance

FAC_LABELS = dict(FACILITIES)


def score_school(school, p):
    """Calculate rule-based weighted score (0-100), reasons, and criterion sub-scores.

    Unknown data (e.g. unlisted results or unpinned coords) is left out of the weighted average
    and marked as 'not provided by the school' so schools are never unfairly penalized with a 0.
    """
    parts = []  # tuple: (criterion_name, weight, frac_or_none, text, ok_bool)

    # 1. Fee
    if p.max_fee:
        if school.fee_min is None:
            parts.append(("fee", p.w_fee, None, "Fee not provided by the school", False))
        elif school.fee_min <= p.max_fee:
            frac, ok = 1.0, True
            text = f"Fee from Rs. {school.fee_min:,} fits your budget"
            parts.append(("fee", p.w_fee, frac, text, ok))
        else:
            over = (school.fee_min - p.max_fee) / p.max_fee
            frac, ok = max(0.0, 1.0 - over), False
            text = f"Fee from Rs. {school.fee_min:,} is above your budget"
            parts.append(("fee", p.w_fee, frac, text, ok))

    # 2. Board
    if p.board:
        if not school.board:
            parts.append(("board", p.w_board, None, "Board not provided by the school", False))
        else:
            ok = (school.board == p.board)
            text = f"Board: {school.board}" + ("" if ok else f" (you wanted {p.board})")
            parts.append(("board", p.w_board, 1.0 if ok else 0.0, text, ok))

    # 3. City
    if p.city:
        if not school.city:
            parts.append(("city", p.w_city, None, "City not provided by the school", False))
        else:
            ok = (school.city.strip().lower() == p.city.strip().lower())
            text = f"City: {school.city}" + ("" if ok else f" (you wanted {p.city})")
            parts.append(("city", p.w_city, 1.0 if ok else 0.0, text, ok))

    # 4. Facilities
    wanted_fac = set(p.facility_list)
    if wanted_fac:
        have_fac = set(school.facility_list)
        hit = wanted_fac & have_fac
        missing = [FAC_LABELS.get(f, f) for f in sorted(wanted_fac - have_fac)]
        text = f"Facilities: {len(hit)} of {len(wanted_fac)} you wanted"
        if missing:
            text += f" (missing: {', '.join(missing)})"
        parts.append(("facilities", p.w_facilities, len(hit) / len(wanted_fac), text, not missing))

    # 5. Specialities
    wanted_spec = set(p.speciality_list)
    if wanted_spec:
        have_spec = set(school.specialities)
        if not have_spec:
            parts.append(("specialities", p.w_specialities, None, "Specialities not provided by the school", False))
        else:
            hit = wanted_spec & have_spec
            missing = sorted(wanted_spec - have_spec)
            text = f"Specialities: {len(hit)} of {len(wanted_spec)} you wanted"
            if missing:
                text += f" (missing: {', '.join(missing)})"
            parts.append(("specialities", p.w_specialities, len(hit) / len(wanted_spec), text, not missing))

    # 6. Results (Latest year average)
    if getattr(p, "w_results", None):
        if school.results:
            latest_year = max(r.year for r in school.results)
            year_results = [r for r in school.results if r.year == latest_year]
            avg_pct = sum(r.pass_percentage for r in year_results) / len(year_results)
            frac = min(1.0, max(0.0, avg_pct / 100.0))
            text = f"Board Results: {avg_pct:.1f}% avg in {latest_year} (Reported by school, not verified)"
            parts.append(("results", p.w_results, frac, text, True))
        else:
            parts.append(("results", p.w_results, None, "Board results not provided by the school", False))

    # 7. Distance
    if getattr(p, "max_distance", None) and p.latitude is not None and p.longitude is not None:
        if school.latitude is not None and school.longitude is not None:
            dist = haversine_distance(p.latitude, p.longitude, school.latitude, school.longitude)
            if dist is not None:
                if dist <= p.max_distance:
                    frac = max(0.0, 1.0 - (dist / p.max_distance))
                    ok = True
                    text = f"Distance: {dist} km away (within {p.max_distance} km limit)"
                else:
                    frac = 0.0
                    ok = False
                    text = f"Distance: {dist} km away (exceeds {p.max_distance} km limit)"
                parts.append(("distance", p.w_distance, frac, text, ok))
            else:
                parts.append(("distance", p.w_distance, None, "Location not provided by the school", False))
        else:
            parts.append(("distance", p.w_distance, None, "Location not provided by the school", False))

    if not parts:
        return 0, [], {}

    # Calculate weighted score only over criteria with known data
    known_parts = [item for item in parts if item[2] is not None]
    total_weight = sum(w for _c, w, _f, _t, _o in known_parts)
    if total_weight > 0:
        score = round(100.0 * sum(w * f for _c, w, f, _t, _o in known_parts) / total_weight)
    else:
        score = 0

    reasons = [(text, (ok if frac is not None else None)) for _c, _w, frac, text, ok in parts]
    sub_scores = {c: (round(frac * 100) if frac is not None else None) for c, _w, frac, _t, _o in parts}

    return score, reasons, sub_scores


def rank_schools(p):
    query = db.select(School).filter(School.status == "approved", School.is_suspended.is_(False))

    # Hard filters
    if getattr(p, "admission_only", False):
        query = query.filter(School.admission_open.is_(True))

    if p.class_needed:
        query = query.filter(School.class_from <= p.class_needed, School.class_to >= p.class_needed)

    results = []
    for school in db.session.scalars(query).all():
        score, reasons, sub_scores = score_school(school, p)
        results.append({
            "school": school,
            "score": score,
            "reasons": reasons,
            "sub_scores": sub_scores,
        })

    results.sort(key=lambda r: (-r["score"], r["school"].name))
    return results
