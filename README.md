# EduHive - Verified Professional Platform for Indian Schools

EduHive is a verified, LinkedIn-style platform designed for the Indian school education ecosystem. Principals register their schools with official verification documents (CBSE/ICSE affiliation, state recognition, principal ID). Platform administrators review and approve schools. Verified schools build rich public profiles, publish posts and events, connect with peer institutions, and receive admission inquiries from parents and students. Families search schools, discover nearby institutions with geospatial radius mapping, and receive transparent, explainable rankings matched to their criteria using **rule-based weighted scoring** (never artificial intelligence or machine learning).

---

## 1. Quick Setup (10 Lines)

```cmd
git clone <repo-url> EduHive
cd EduHive
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
flask db upgrade
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.session.execute(db.text('UPDATE users SET is_verified = 1')); db.session.commit()"
flask create-admin
flask run
```

---

## 2. Environment Variables (.env)

| Variable | Description | Example |
| :--- | :--- | :--- |
| `SECRET_KEY` | Cryptographic secret for session cookies, CSRF tokens, and signed tokens | `super-secret-random-key` |
| `DATABASE_URL` | SQLAlchemy MySQL connection string via PyMySQL | `mysql+pymysql://user:pass@localhost:3306/eduhive` |
| `MAIL_SERVER` | *(Optional)* SMTP mail server host; if empty, emails print cleanly to terminal | `smtp.gmail.com` |
| `MAIL_PORT` | SMTP port | `587` |
| `MAIL_USE_TLS` | Enable TLS encryption | `True` |
| `MAIL_USERNAME` | SMTP auth username | `user@example.com` |
| `MAIL_PASSWORD` | SMTP app password | `app-specific-password` |

---

## 3. Project Architecture & File Directory

```
EduHive/
├── app/
│   ├── __init__.py          # Flask application factory, extension initializations, CLI commands
│   ├── models.py            # SQLAlchemy 2 data models (User, School, Post, Event, Connection, etc.)
│   ├── decorators.py        # RBAC decorator @role_required
│   ├── admin/               # Admin blueprint: school approvals, suspensions, users list, post moderation
│   │   ├── forms.py         # RejectForm
│   │   └── routes.py        # /admin/schools, /admin/users, /admin/posts/<id>/delete
│   ├── auth/                # Auth blueprint: signup, login, email verification, password reset
│   │   ├── forms.py         # SignupForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
│   │   ├── email.py         # SMTP sender with console fallback
│   │   └── routes.py        # /signup, /login, /verify-email/<token>, /forgot-password
│   ├── content/             # Posts & Events blueprint
│   │   ├── forms.py         # PostForm (with image), EventForm, EventRegisterForm
│   │   └── routes.py        # /school/posts/new, /posts/<id>/like, /school/events/new, /events/<id>/join
│   ├── follows/             # Social follow & activity feed blueprint
│   │   └── routes.py        # /schools/<id>/follow, /feed (Following & Connected Network tabs)
│   ├── matches/             # Rule-based discovery, matching, shortlist & compare
│   │   ├── forms.py         # PriorityForm (weights 1-5, budget, board, distance, specialities)
│   │   ├── scoring.py       # Rule-based weighted scoring algorithm & rank_schools()
│   │   └── routes.py        # /priorities, /matches (with live sliders), /shortlist, /compare
│   ├── schools/             # School profiles, documents, connections, nearby map, inquiries
│   │   ├── forms.py         # SchoolForm, ProfileForm, LogoForm, GalleryForm, InquiryForm, InquiryReplyForm
│   │   ├── geocode.py       # Nominatim geocoding, pincode lookup, Haversine distance formula
│   │   ├── images.py        # Pillow EXIF-stripping, thumbnailing, safe upload storage
│   │   ├── options.py       # Facilities, boards, mediums, and specialities taxonomy
│   │   ├── uploads.py       # Document magic-byte checking (%PDF, %PNG, JPEG) & storage
│   │   └── routes.py        # /school/register, /school/profile, /schools/nearby, /school/connections, /school/inquiries
│   ├── static/              # CSS styles (Fraunces & DM Sans, honeycomb theme, WCAG AA contrast)
│   └── templates/           # Jinja2 templates organized by blueprint
├── migrations/              # Alembic / Flask-Migrate database migrations
├── tests/                   # Pytest test suite (24 automated tests + url_for audit)
│   ├── conftest.py          # Pytest fixtures, test client, user & school factories
│   ├── test_audit.py        # Automated active url_for route audit
│   ├── test_auth.py         # Auth & email verification tests
│   ├── test_content.py      # Posts & events tests
│   ├── test_errors.py       # HTTP 403, 404, 500 handler tests
│   ├── test_follows.py      # Follow & unfollow tests
│   ├── test_matches.py      # Rule-based matching & weighting logic tests
│   ├── test_permissions.py  # 6-role permission matrix & failure paths tests
│   ├── test_school_extras.py# Gallery, logo, results & admission tests
│   └── test_smoke.py        # Complete end-to-end user & school smoke flow test
├── uploads/                 # Storage for private documents and photos (outside static)
├── audit_url_for.py         # Standalone AST-based endpoint validation script
├── config.py                # Development, Testing, and Production Config classes
├── requirements.txt         # Pinned Python package dependencies
└── run.py                   # Development server entry point
```

---

## 4. Technical Decisions & Trade-Offs

1. **Rule-Based Weighted Scoring vs Machine Learning**:
   Matching is strictly explainable rule-based scoring calculated as `\sum (weight \times score) / \sum weight`. Parents can inspect exact reasons for each score ("Fee fits your budget", "Missing: Science lab"). Machine learning was deliberately rejected because school admissions require 100% deterministic, explainable, and verifiable criteria without hallucinations or unexplainable black-box weights.
2. **Treatment of Missing School Data**:
   If a school has not provided their board exam results or pinned their coordinates, that criterion is **excluded from the average** and flagged as "Not provided by the school". It is never penalized as a 0, preventing newer verified schools from being unfairly buried.
3. **Canonical Pair Constraint for School Connections**:
   Connections store `school_low_id = min(id1, id2)` and `school_high_id = max(id1, id2)` with a unique constraint `uq_connection_pair`. This ensures exactly one database row per school pair regardless of who initiated the request.
4. **Pillow EXIF Stripping & Non-Static Storage**:
   Photos uploaded by schools or post authors are stripped of EXIF metadata (GPS tags, device IDs) using Pillow and saved with UUID filenames in `/uploads` outside `static/`. Serving routes (`/school/photo/<id>`, `/posts/<id>/photo`) perform role checks so suspended or unapproved schools cannot leak media publicly.
5. **Single-Use Signed Tokens without Extra DB Columns**:
   Password reset tokens embed `{"id": user.id, "hash": user.password_hash[:12]}` inside an `itsdangerous.URLSafeTimedSerializer` with a 1-hour expiry. When the password is changed, the hash slice changes, rendering previous tokens immediately invalid for reuse without requiring extra token tables.

---

## 5. Five-Minute Placement Viva Demo Walkthrough

| Time | Action | What to Explain to the Examiner |
| :--- | :--- | :--- |
| **0:00 - 1:00** | **Signup & Email Verification**<br>Register Principal Sharma (`principal@indore.edu`), show token printed in terminal, verify email, choose School role. | "EduHive requires email verification before school registration to prevent spam. Tokens are cryptographically signed with itsdangerous." |
| **1:00 - 2:00** | **Document Upload & Admin Verification**<br>Upload PDF affiliation certificates. Log in as admin (`flask create-admin`), review documents, and approve the school. | "Uploads live outside `static/` with magic-byte validation (`%PDF`). Unapproved schools are invisible to the public." |
| **2:00 - 3:00** | **Rich Profile & Social Network**<br>Fill profile with fees, board results (94.5%), facilities, and map location. Post an event with 50-seat capacity. | "Draggable Leaflet map records coordinates in India. Posts and events allow schools to connect with other schools and families." |
| **3:00 - 4:00** | **Parent Matching with Live Sliders**<br>Log in as parent, fill priorities (budget &#8377;50,000, CBSE, Class 6). Open Matches and drag live importance sliders. | "Explainable rule-based weighted ranking. Moving sliders recalculates scores instantly in vanilla JS without server roundtrips." |
| **4:00 - 5:00** | **Shortlist, Compare & Inquiry**<br>Shortlist 2 schools, compare side-by-side table, send admission inquiry, log into school inbox and reply. | "Complete end-to-end admissions funnel: discovery -> comparison -> direct admission inquiry inbox with replies." |

---

## 6. Five-Parent Matching Test Plan (Explainable Rule-Based Verification)

| Parent Scenario | Priorities Input | Expected Top Match | Why (Rule Explanation) |
| :--- | :--- | :--- | :--- |
| **Parent 1: Strict Budget** | Max fee &#8377;35,000 (`w_fee=5`), any board | School A (Fee &#8377;30,000) | School A receives 100% on fee (weight 5). School B (Fee &#8377;65,000) is heavily penalized for exceeding budget. |
| **Parent 2: Board-Focused** | Board ICSE (`w_board=5`), no fee limit | School C (ICSE Board) | School C receives 100% on board match. CBSE schools receive 0% on board criterion. |
| **Parent 3: Distance / Proximity** | Pincode 452010, Max distance 5 km (`w_distance=5`) | School A (2.3 km away) | Haversine formula scores distance linearly `1 - (d / max_d)`. Schools > 5 km receive 0 on distance. |
| **Parent 4: Sports & Labs** | Facilities: Sports, Science Lab (`w_facilities=5`) | School with both facilities | Matched count / wanted count = 2/2 (100%). Schools with only 1 facility score 50%. |
| **Parent 5: High Academic Results** | Board Results (`w_results=5`) | School with 96% board pass rate | Latest year average pass percentage directly drives results sub-score. Schools without results are excluded from average. |

---

## 7. Automated Testing & Verification

Run the entire test suite and link audit:

```cmd
venv\Scripts\python.exe -m pytest -v
venv\Scripts\python.exe audit_url_for.py
```

- **24 automated tests** covering authentication, registration, file magic bytes, permissions matrix, capacity limits, connections, matching, and end-to-end smoke flow.
- **0 broken `url_for` endpoints** verified by AST template code audit.
