# Trekking Management System — Complete Code Explanation

A **Flask web app** for managing trekking expeditions with three roles: **Admin**, **Staff (guides)**, and **User (trekkers)**.

**The big picture in one sentence:** requests hit a route in `app.py`, the route checks the logged-in user's role, reads/writes rows through the models in `models.py`, and renders a template — with `config.py` supplying secrets/database settings and `seed.py` providing demo data.

---

## 1. `config.py` — App configuration

This file decides the app's secret key, database location, and cookie security.

### `_load_secret_key()`
Returns the key used to sign session cookies (so nobody can forge a login session). It tries three sources in order:
1. The `SECRET_KEY` environment variable (for production/Vercel).
2. A `.secret_key` file saved locally (created automatically on first run).
3. A random in-memory key if the filesystem is read-only (Vercel serverless).

### `_database_uri()`
Decides where the database lives:
- If `DATABASE_URL` is set (a hosted Postgres), it uses that — fixing the `postgres://` → `postgresql://` scheme that SQLAlchemy needs.
- Otherwise it creates a local SQLite file at `database/trekking.db`, falling back to `/tmp` on Vercel where the project folder is read-only.

### `class Config`
The settings object Flask loads. Sets `SECRET_KEY`, the database URI, and three cookie protections:
- `SESSION_COOKIE_HTTPONLY` — JavaScript can't steal the cookie (limits XSS damage).
- `SESSION_COOKIE_SAMESITE = 'Lax'` — blocks cross-site request forgery.
- `SESSION_COOKIE_SECURE` — HTTPS-only cookie, off by default so localhost works.

---

## 2. `models.py` — Database tables

Defines the five database tables using SQLAlchemy. Each class = one table; each `db.Column` = one column.

### `User`
Everyone who logs in: admins, staff, and trekkers, distinguished by the `role` column. Stores name, email (unique), phone, hashed password (never plain text), `is_blacklisted` flag, and creation time.
- Relationships: one user → many `bookings`; one staff user → one `staff_profile`.

### `StaffProfile`
Extra info only staff have: contact details, `approval_status` (Pending / Approved / Rejected — new guides can't log in until an admin approves them), specializations, and a counter of assigned treks. Linked one-to-one to `User` via `user_id`.

### `Trek`
A trek expedition: name, location, difficulty (Easy/Moderate/Hard), duration, description, `available_slots` (seats left), start/end dates, `status` (Pending / Approved / Open / Closed / Started / Completed), and `assigned_staff_id` pointing at the guide's user record.

### `Booking`
The link between a trekker and a trek: who booked what, when, and its `status` (Booked / Cancelled / Completed).

### `Review`
A trekker's 1–5 star rating and comment for a trek. (The table exists, but no route in `app.py` uses it yet — it's an unused feature.)

Each model's `__repr__()` returns a readable string for debugging, and `__init__()` passes arguments straight to SQLAlchemy.

---

## 3. `app.py` — The main application (all routes)

The heart of the project. It creates the Flask app, connects the database, and sets up:
- **Flask-Login** — session management (who is logged in).
- **CSRFProtect** — every POST form needs a valid token.
- **Rate limiter** — blocks brute-force attempts by IP address.

### Helper functions

| Function | What it does |
|---|---|
| `is_password_strong(password)` | Password policy: at least 8 characters, one letter, one number. Returns `(True, "")` or `(False, "reason")`. |
| `resolve_assigned_staff_id(raw_value, approved_staff)` | Safely converts the guide dropdown value from a form into a valid staff ID. Empty = no guide; invalid or non-approved ID raises a friendly error instead of crashing. |
| `load_user(user_id)` | Called by Flask-Login on every request to load the logged-in user from the DB. Returns `None` if the user is blacklisted, which instantly logs them out. |

### Public routes

| Function | URL | What it does |
|---|---|---|
| `index()` | `/` | The landing page. |
| `login()` | `/login` | Unified login for all three roles. Checks email + password hash, blocks blacklisted accounts, blocks unapproved staff, then redirects each role to its own dashboard. Rate-limited to 10 POSTs/minute. |
| `register()` | `/register` | Registration with a role selector (user or staff). Validates all fields, matching passwords, and password strength; staff accounts start as "Pending" with a `StaffProfile` awaiting admin approval. Uses a deliberately generic duplicate-email message so attackers can't check which emails are registered. |
| `register_user()` / `register_staff()` | `/register/user`, `/register/staff` | Old URLs that just redirect to `/register` so old links don't break. |
| `logout()` | `/logout` | Ends the session. |

### Admin routes (each first checks `current_user.role == 'admin'`)

| Function | URL | What it does |
|---|---|---|
| `admin_dashboard()` | `/admin/dashboard` | Counts treks, bookings, users, staff, and pending staff; shows the 5 latest bookings. |
| `admin_search()` | `/admin/search` | One search box that queries treks, trekkers, staff, and bookings at once with SQL `LIKE`. |
| `admin_reports()` | `/admin/reports` | Builds three chart datasets: bookings per trek, trek difficulty split, and booking status split. |
| `admin_settings()` | `/admin/settings` | Admin edits their own name/email/phone and optionally changes password (requires the current password + strength check). |
| `manage_treks()` | `/admin/treks` | Trek list with search (by name or ID) and filters (difficulty, status, location). |
| `create_trek()` | `/admin/treks/create` | New trek form. Validates numbers are positive, dates parse and end ≥ start, and the assigned guide is approved. Then updates that guide's trek counter. |
| `edit_trek(trek_id)` | `/admin/treks/edit/<id>` | Same validation as create, but updates an existing trek and refreshes the trek counters of both the old and new guide. |
| `delete_trek(trek_id)` | `/admin/treks/delete/<id>` | Deletes a trek (its bookings go too, via cascade) and updates the guide's counter. |
| `manage_staff()` | `/admin/staff` | Staff directory in four tabs (Pending/Approved/Rejected/Blacklisted) with counts and search. |
| `approve_staff(staff_id)` / `reject_staff(staff_id)` | `/admin/staff/approve/<id>`, `/admin/staff/reject/<id>` | Set a guide's approval status; approval is what lets them log in. |
| `manage_users()` | `/admin/users` | Trekker list with search. |
| `toggle_blacklist_user(user_id)` | `/admin/toggle-blacklist/<id>` | Flips a user's blacklist flag (admins can't blacklist admins). Blacklisted users are logged out automatically by `load_user()`. |
| `view_bookings()` | `/admin/bookings` | All bookings with search, status filter, and Booked/Cancelled/Completed counters. |
| `admin_cancel_booking(booking_id)` | `/admin/bookings/cancel/<id>` | Cancels an active booking and gives the seat back (`available_slots += 1`). |

### Staff routes (each checks `role == 'staff'`; most also check the profile is Approved)

| Function | URL | What it does |
|---|---|---|
| `staff_dashboard()` | `/staff/dashboard` | Lists treks assigned to this guide with participant counts and stat cards. |
| `staff_participants()` | `/staff/participants` | All bookings across all of this guide's treks. |
| `staff_profile()` | `/staff/profile` | Guide edits their own contact info and specializations. |
| `staff_update_slots(trek_id)` | `/staff/treks/<id>/update-slots` | Guide changes seat capacity — but only on treks assigned to them (ownership check). |
| `staff_change_status(trek_id, action_name)` | `/staff/treks/<id>/change-status/<action>` | Guide opens / closes / starts / completes a trek. Completing also marks every active booking on it as Completed. |
| `staff_trek_participants(trek_id)` | `/staff/treks/<id>/participants` | The "Manage Trek" page: trek info + participant list, with the same ownership check. |

### User (trekker) routes

| Function | URL | What it does |
|---|---|---|
| `user_dashboard()` | `/explorer` | Search and filter **Open** treks, plus a preview of their 5 latest bookings. |
| `browse_treks()` | `/treks` | Full browse page, same filtering. |
| `trek_history()` | `/history` | Their Completed bookings only. |
| `trek_details(trek_id)` | `/trek/<id>` | One trek's detail page, plus whether this user already booked it. |
| `book_trek(trek_id)` | `/trek/<id>/book` | The most interesting function — see below. |
| `cancel_booking(booking_id)` | `/booking/<id>/cancel` | Cancel your own booking (or admin can cancel any); the seat is released back. |
| `my_bookings()` | `/my-bookings` | All of this user's bookings. |
| `edit_profile()` | `/profile/edit` | Trekker updates name/email/phone with a duplicate-email check. |

**How `book_trek()` works:** After checking the user isn't blacklisted, the trek is Open, and they don't already hold an active booking, it claims a seat with a **single atomic SQL UPDATE** (`decrement slots only WHERE slots > 0`). This prevents two people booking the last seat simultaneously — no overbooking possible, and slots can never go negative. If the user had a Cancelled booking for that trek, it's reactivated instead of duplicated.

### Error handlers

| Function | What it does |
|---|---|
| `page_not_found(e)` | 404s return JSON for `/api/...` paths, otherwise the home page. |
| `handle_csrf_error(e)` | Friendly redirect when a form's CSRF token is missing/expired instead of an ugly 400 page. |
| `handle_rate_limit(e)` | Friendly "too many attempts" message on hitting a rate limit. |

### JSON API endpoints

| Function | URL | What it does |
|---|---|---|
| `api_get_treks()` | `GET /api/treks` | Open treks as JSON (all treks if you're an admin). |
| `api_get_trek(trek_id)` | `GET /api/treks/<id>` | One trek as JSON; non-open treks are hidden from non-admins. |
| `api_get_bookings()` | `GET /api/bookings` | All bookings as JSON, admin-only. |
| `api_get_users()` | `GET /api/users` | All users as JSON, admin-only. |

### Startup

**`init_db()`** — Creates all tables and seeds the default admin account. The password comes from the `ADMIN_PASSWORD` env var, or a strong random one is generated and printed once (so there's no well-known "admin123" default). If the env var later changes, it re-syncs the stored password. It runs **at import time** (not just in `__main__`) so it also works on Vercel, which imports `app` rather than running the file.

**The `if __name__ == '__main__'` block** — Local development only: runs the server on `127.0.0.1:5000`, debug off unless `FLASK_DEBUG=1`.

---

## 4. `seed.py` — Demo data script

### `seed_db()`
Run manually (`python seed.py`) to fill the database with test data:
- The default admin: `ganesh.agarwal@pw.live` / `zxcvbnm1`
- Two guides: John (approved), Jane (pending)
- Three trekkers: Alice, Bob, and Charlie (blacklisted)
- Three treks: Himalayan Valley, Western Ghats, Everest Base Camp
- Two bookings (one Booked, one Cancelled)

It checks first and skips if data already exists, and rolls back on any error. Note it uses `db.session.flush()` after adding a staff user — that assigns the user an ID *before* commit, so the `StaffProfile` can reference it.

---

## 5. The other pieces (no functions, but worth knowing)

- **`templates/`** — 24 HTML pages (Jinja2). `base.html` and `dash_base.html` are shared layouts; the rest are the pages each route renders, organized into `admin/`, `staff/`, `user/` folders matching the roles.
- **`static/css/styles.css`** — All the styling.
- **`vercel.json`** — Tells Vercel to build `app.py` with the Python runtime, bundle `templates/` and `static/`, and route every URL to the app. Deleting it breaks the Vercel deployment (local runs are unaffected).
- **`__pycache__/`** — Auto-generated compiled bytecode; safe to delete, Python recreates it.
- **`.claude/`** — Claude Code configuration only; no effect on the app.

---

## Viva quick-prep: the three functions worth knowing deeply

1. **`book_trek()` (`app.py`)** — the atomic seat-claim UPDATE that makes overbooking impossible even with simultaneous requests.
2. **`load_user()` (`app.py`)** — returning `None` for blacklisted users is what force-logs them out on their very next request.
3. **`init_db()` (`app.py`)** — runs at import time because Vercel imports the `app` object and never executes the `__main__` block.
