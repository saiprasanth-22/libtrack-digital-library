# LibTrack — Digital Library Management System

LibTrack is a digital library management system for college students and
librarians, built as a DBMS project with **Python, Django, MySQL, HTML, CSS and
JavaScript**.

The catalogue, availability, dashboards and reports are all rendered from a
MySQL database through the Django ORM. No student name, book count, issue
record or dashboard statistic is hard-coded in the interface.

- Live site (front-end reference): <https://libtrack-digital-library.vercel.app/>
- Documentation: [Database schema](docs/DATABASE_SCHEMA.md) ·
  [Mermaid ER diagram](docs/DATABASE_SCHEMA.md#1-entity-relationship-diagram) ·
  [Catalogue import](docs/CATALOGUE_IMPORT.md) ·
  [Cover-art pipeline](docs/COVER_ART.md) ·
  [Study Buddy](docs/STUDY_BUDDY.md)

---

## 1. Technology

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | Django 5.2 |
| Database | MySQL 8 (SQLite fallback for local demos only) |
| Front-end | Django templates, hand-written CSS, vanilla JavaScript |
| Static files | WhiteNoise |
| MySQL driver | PyMySQL |
| Images | Pillow (book cover uploads) |

No React, Next.js, Node, Firebase, Supabase or any other stack is used.

---

## 2. Running the project locally

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure the environment
cp .env.example .env               # Windows: copy .env.example .env
# Load it however you prefer (python-dotenv, your shell, or your IDE).

# 4. Create the tables
python manage.py migrate

# 5. Load demonstration data
python manage.py seed_demo_data

# 6. Import the BCA academic catalogue (120 titles, scheme-aware)
python manage.py import_bca_catalogue

# 7. Generate the original cover artwork for every title
python manage.py generate_covers

# 8. Collect static files
python manage.py collectstatic --noinput

# 9. Start the server
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

**If you skip step 3**, the project still runs and falls back to a local
`db.sqlite3` so you can demonstrate it without a database server.

---

## 3. MySQL setup

Create an empty database and a user, then put the credentials in `.env`:

```sql
CREATE DATABASE libtrack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'libtrack_user'@'localhost' IDENTIFIED BY 'your-strong-password';
GRANT ALL PRIVILEGES ON libtrack.* TO 'libtrack_user'@'localhost';
FLUSH PRIVILEGES;
```

```env
MYSQL_DATABASE=libtrack
MYSQL_USER=libtrack_user
MYSQL_PASSWORD=your-strong-password
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
```

When `MYSQL_DATABASE` is set, Django uses MySQL automatically. The connection
uses `utf8mb4` and `STRICT_TRANS_TABLES`, so bad data raises an error instead of
being silently truncated. `PyMySQL` is installed as the MySQLdb driver in
`libtrack/__init__.py`, so no extra configuration is needed.

Never commit `.env`. It is listed in `.gitignore`; only `.env.example` is
tracked.

---

## 4. Demo accounts

Created by `python manage.py seed_demo_data`. **Local demonstration only.**

| Role | Username | Name | Password |
|---|---|---|---|
| Student | `maya.rao` | Maya Rao | `LibTrackDemo2026!` |
| Student | `arjun.nair` | Arjun Nair | `LibTrackDemo2026!` |
| Student | `leela.venkat` | Leela Venkat | `LibTrackDemo2026!` |
| Librarian | `library.admin` | Library Administrator | `LibTrackDemo2026!` |

Set `LIBTRACK_DEMO_PASSWORD` before seeding any shared environment. The seed
command only sets a password when it *creates* an account, so re-running it
never resets a password you have changed.

For a real deployment create the librarian without demo data:

```bash
python manage.py createsuperuser
```

then set `is_staff` (the command already does this) and use `/admin/` for
Django's built-in back office.

---

## 5. Demo walkthrough (5 minutes)

1. **Landing page** — headline numbers come from the database: 14 titles,
   40 copies, availability count, registered students.
2. **Sign in as `maya.rao`** — the dashboard greets Maya by name and shows
   *her* numbers: active loans, due soon, returned, overdue.
3. **Open "Database System Concepts"** — the availability panel reads
   "4 of 5 copies", taken live from the `BookCopy` table. Borrow it; the
   count drops to 3 and a loan record appears on the dashboard.
4. **Try to borrow it again** — blocked: *"You already have this title on loan."*
5. **Borrow three books, then a fourth** — blocked: *"You already have 3 books
   on loan."* Change `LIBRARY_MAX_ACTIVE_LOANS` in `.env` to show the limit is
   configuration, not code.
6. **Renew a book** — due date moves out by 7 days. Renew again — blocked at
   the configured maximum of one renewal.
7. **Return a book** — availability goes back up by exactly one.
8. **Sign out, sign in as `library.admin`** — the librarian dashboard shows
   totals, copies, students, active and overdue loans, pending requests and
   most-borrowed titles, all from aggregate queries.
9. **Circulation desk** — issue a book to a student, approve or reject the
   pending request, and record a return.
10. **Reports** — set a date range and see active loans, returns, overdue
    books, most-borrowed titles, borrowing by course and inventory.

---

## 6. Features

### Student
- Registration with validation (duplicate email, duplicate registration
  number, password strength, semester range)
- Login / logout (POST-only), Django password hashing
- Dashboard with the authenticated student's real name and counters:
  active loans, due soon, overdue, returned, pending requests
- Upcoming due dates with days remaining
- Book catalogue: search by title, author, ISBN, publisher, keyword or
  category; filter by category and availability; sort by title, author,
  newest or availability; pagination
- Book details with full bibliographic record and live availability
- Book detail tabs — Overview, Availability (copy-level shelf status),
  Digital resources and Reviews — as a real ARIA tablist with arrow-key
  navigation; every panel is present in the HTML and stays visible without
  JavaScript
- Borrow an available book, or request one that is out
- Renew (once, by the configured number of days) and return
- Borrowing history with status tabs
- Reading list (save / unsave books)
- Rate and review a title you have borrowed and returned (1–5 stars, one
  review per student per title); the average and count feed the tab badge
- Profile editing and a Django password-change flow
- Digital materials list with search

### Librarian / Admin
- Dashboard: titles, copies, available copies, students, active loans,
  overdue loans, pending requests, most-borrowed titles, live activity feed
- Book CRUD: add, edit, delete (retire when history exists), search
- Physical copy management: add copies, change status, shelf locations
- Inventory validation — invalid copy counts are rejected
- Student management: search, register a student at the desk, borrowing
  history per student, activate/deactivate accounts, and remove a student
  (deleted outright when they have no history, deactivated when they do)
- Circulation desk: issue a book, approve or reject requests, record returns
- Digital material management: add, edit, delete, visibility, file validation
- Reports: active loans, returns, overdue, most borrowed, per-course
  borrowing, inventory availability, date-range filtering
- Django admin at `/admin/` for direct table access

### Shared
- CSRF protection on every form
- `login_required` and role checks on every protected route
- Every mutating route is POST-only, so a link prefetch can never change data
- Redirect targets from the client are host-validated (`_safe_next`), so no
  form can be turned into an open redirect
- Django messages for all outcomes
- Accessible labels, help text and inline errors on every form field
- Empty states that match the existing design
- Responsive from 360 px to desktop

### Reference coverage

Every function in the reference video has a working equivalent in LibTrack.
The full function-by-function mapping — reference feature, LibTrack route,
responsible role, status and the automated test that proves it — is in
[`docs/REFERENCE_COVERAGE.md`](docs/REFERENCE_COVERAGE.md).

Summary: **31 reference functions identified, 31 implemented, 0 uncovered**,
plus 12 extensions beyond the reference. Three reference patterns were
deliberately redesigned rather than copied (unsafe student deletion, unsafe
book deletion, `GET`-reachable mutating links).

### Academic catalogue

The collection is curated for the BCA programme (2023–2026 NEP cohort,
Bengaluru North University) through a scheme-aware structure:
`Course → CurriculumScheme → Semester → Subject → BookSubjectMapping → Book`.

- **120 titles**, 173 authors, 38 curriculum subjects across six semesters,
  135 book-to-subject mappings and 17 subject-linked digital materials —
  imported idempotently from versioned CSV under `data/bca/` (see
  [docs/CATALOGUE_IMPORT.md](docs/CATALOGUE_IMPORT.md)).
- Confidence labels (`verified-current`, `verified-syllabus`,
  `curriculum-supported`) from the
  [curriculum research](docs/BCA_CURRICULUM_RESEARCH.md) are stored on
  subjects and mappings; nothing provisional is presented as officially
  prescribed. Recommended is the strongest book status used; no seeded book
  is claimed as "prescribed".
- Combinable server-side filters: course, curriculum, semester, subject,
  classification, resource type, recommendation status, category,
  availability and search across academic metadata (subject names, codes and
  course names included), with pagination that preserves every filter.
- The path BCA → Semester V → Statistical Computing and R → Recommended
  books is four selects in one form.
- Original text-free cover artwork is generated deterministically for every
  title (see [docs/COVER_ART.md](docs/COVER_ART.md)).

### Study Buddy (foundation)

A future AI study companion, shipped scaffolded and **disabled**:
context selectors (course → semester → subject → book → topic), seven
learning modes, a provider-independent service boundary, and an honest
"awaiting configuration" state. No network call is possible until the
`STUDY_BUDDY_*` environment variables are set; see
[docs/STUDY_BUDDY.md](docs/STUDY_BUDDY.md).

---

## 7. Business rules

Configured in `libtrack/settings.py` under `LIBRARY_RULES` and overridable with
environment variables — no magic numbers in the views or services.

| Rule | Default | Environment variable |
|---|---|---|
| Standard loan duration | 14 days | `LIBRARY_LOAN_DAYS` |
| Maximum active loans per student | 3 | `LIBRARY_MAX_ACTIVE_LOANS` |
| Maximum renewals per loan | 1 | `LIBRARY_MAX_RENEWALS` |
| Renewal extension | 7 days | `LIBRARY_RENEWAL_DAYS` |
| "Due soon" window | 7 days | `LIBRARY_DUE_SOON_DAYS` |
| Catalogue page size | 12 | `LIBRARY_PAGE_SIZE` |

- A book with no free copy cannot be issued.
- A student cannot hold two active loans for the same title.
- Issuing decreases available copies exactly once; returning increases it
  exactly once; a second return is rejected.
- Overdue is **derived** from `due_at` whenever the book has not been returned.
- A deactivated student cannot borrow or request; existing loans are kept.
- A due date earlier than the issue date is refused by the service *and* by a
  database `CHECK` constraint.

---

## 8. Routes

### Public
| Method | Path | Name | Purpose |
|---|---|---|---|
| GET | `/` | `core:home` | Landing page with live statistics |
| GET | `/discover/` | `core:discover` | Search, filter, sort, paginate the catalogue |
| GET | `/materials/` | `core:materials` | Digital learning materials |
| GET | `/books/<slug>/` | `core:book_detail` | Book details, tab panels and availability |

### Authentication
| Method | Path | Name | Purpose |
|---|---|---|---|
| GET/POST | `/accounts/login/` | `core:login` | Sign in |
| GET/POST | `/accounts/register/` | `core:register` | Student registration |
| POST | `/accounts/logout/` | `core:logout` | Sign out |
| GET | `/dashboard/` | `core:dashboard` | Sends each role to its own home |

### Student (login required, non-staff)
| Method | Path | Name | Purpose |
|---|---|---|---|
| GET | `/student/` | `core:student` | Dashboard |
| GET | `/student/loans/` | `core:student_loans` | Borrowing history (`?tab=`) |
| GET | `/student/profile/` | `core:student_profile` | Profile, history, password change |
| POST | `/student/profile/update/` | `core:student_profile_update` | Save profile |
| GET/POST | `/student/password/` | `core:student_password` | Change password |
| GET | `/student/password/done/` | `core:student_password_done` | Confirmation |
| POST | `/books/<slug>/borrow/` | `core:borrow_book` | Borrow an available book |
| POST | `/books/<slug>/request/` | `core:request_book` | Request an unavailable book |
| POST | `/books/<slug>/save/` | `core:save_book` | Save / unsave to reading list |
| POST | `/books/<slug>/review/` | `core:book_review` | Publish or update a review of a returned title |
| POST | `/loans/<id>/renew/` | `core:renew_loan` | Renew a loan |
| POST | `/loans/<id>/return/` | `core:return_loan` | Return a loan |

### Librarian (login required, staff)
| Method | Path | Name | Purpose |
|---|---|---|---|
| GET | `/librarian/` | `core:librarian` | Dashboard |
| GET/POST | `/librarian/books/` | `core:librarian_books` | Catalogue list, search and add |
| GET/POST | `/librarian/books/<pk>/edit/` | `core:librarian_book_edit` | Edit a title |
| POST | `/librarian/books/<pk>/delete/` | `core:librarian_book_delete` | Delete or retire |
| GET/POST | `/librarian/books/<pk>/copies/` | `core:librarian_copies` | Manage physical copies |
| GET/POST | `/librarian/students/` | `core:librarian_students` | Search students, register a student at the desk |
| GET | `/librarian/students/<pk>/` | `core:librarian_student_detail` | One student's record |
| POST | `/librarian/students/<pk>/toggle/` | `core:librarian_student_toggle` | Activate / deactivate |
| POST | `/librarian/students/<pk>/delete/` | `core:librarian_student_delete` | Remove, or deactivate when history exists |
| GET/POST | `/librarian/circulation/` | `core:librarian_circulation` | Issue, requests, returns |
| POST | `/librarian/requests/<pk>/approve/` | `core:librarian_request_approve` | Approve a request |
| POST | `/librarian/requests/<pk>/reject/` | `core:librarian_request_reject` | Reject a request |
| GET/POST | `/librarian/materials/` | `core:librarian_materials` | Digital material list and add |
| GET/POST | `/librarian/materials/<pk>/edit/` | `core:librarian_material_edit` | Edit a material |
| POST | `/librarian/materials/<pk>/delete/` | `core:librarian_material_delete` | Remove a material |
| GET | `/librarian/reports/` | `core:librarian_reports` | Reports (`?start=&end=`) |

### Django
| Path | Purpose |
|---|---|
| `/admin/` | Django administration site |

---

## 9. Project structure

```
libtrack/                  Project settings and entry points
  settings.py              Environment-driven configuration, business rules
  urls.py                  Root URL configuration
core/                      Single Django app
  models.py                Data model
  services.py              Transactional circulation logic and report queries
  forms.py                 Django forms with validation
  views.py                 Thin views: querysets in, templates out
  urls.py                  Named routes
  admin.py                 Admin registrations
  context_processors.py    Shares library rules with templates
  migrations/              Schema history
  management/commands/seed_demo_data.py
  test_runner.py           Swaps in plain staticfiles storage during tests
  tests/                   Automated tests
templates/                 Django templates
static/css/                Design system (app.css, product.css, modules.css)
static/js/app.js           UI interactions
static/js/tabs.js          Book detail tab panels (progressive enhancement)
docs/                      Schema, ER diagram, import + cover + Study Buddy docs,
                           reference-coverage matrix, curriculum research
  DATABASE_SCHEMA.md       Tables, relationships, Mermaid ER diagram, 3NF notes
  REFERENCE_COVERAGE.md    Reference video -> LibTrack coverage matrix
```

The project keeps its original single-app (`core`) structure rather than being
split into `accounts` / `catalogue` / `circulation` / `librarian` apps. All four
responsibilities are separated by module inside `core` (`models`, `services`,
`forms`, `views`) and by URL namespace, which keeps the schema, migrations and
templates easier to follow for a single-author project.

---

## 10. Tests

```bash
python manage.py test
```

**216 tests, all passing.** They cover:

- Registration (success, duplicate email, duplicate student number, password
  mismatch, weak password, semester range)
- Login (student, librarian, wrong password, deactivated account, logout)
- Route protection for students and staff, in both directions
- Book creation and validation (negative copies, bad ISBN, duplicate ISBN,
  oversized cover, material without a source, disallowed file type)
- Catalogue search by title, author, ISBN, category; filtering; sorting;
  pagination preserving query parameters
- Successful issue, issue when unavailable, inactive book
- Maximum-loan enforcement and duplicate-loan prevention
- Successful return, duplicate-return prevention, return before issue
- Inventory accuracy across a full borrow/return cycle, and never negative
- Renewal rules (extends, capped, overdue blocked, returned blocked,
  not another student's loan)
- Overdue calculation and status synchronisation
- Deactivated-student restrictions
- Librarian book/copy/student/material management and reports
- Desk registration of a student, and safe student removal
  (deleted when history-free, deactivated when history exists)
- Book detail tab panels: every button wired to a real panel, all panels
  present without JavaScript
- Copy-level availability panel reacting to a real issue
- Reader reviews: publish, edit-instead-of-duplicate, eligibility gated on a
  returned loan, rating bounds, average reaching the tab badge
- Open-redirect rejection on every view that accepts a `next` target
- Seed command idempotency and account-password safety

Other checks:

```bash
python manage.py check                    # system checks
python manage.py makemigrations --check   # no missing migrations
python manage.py collectstatic --noinput  # static files
```

---

## 11. Deployment

### Environment variables required in production

```env
DJANGO_SECRET_KEY=<long random string>
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com

MYSQL_DATABASE=libtrack
MYSQL_USER=libtrack_user
MYSQL_PASSWORD=<strong password>
MYSQL_HOST=<mysql host>
MYSQL_PORT=3306

DJANGO_MEDIA_ROOT=<path or object storage>

LIBRARY_LOAN_DAYS=14
LIBRARY_MAX_ACTIVE_LOANS=3
LIBRARY_MAX_RENEWALS=1
LIBRARY_RENEWAL_DAYS=7

# Optional — Study Buddy stays disabled until all four are set
STUDY_BUDDY_ENABLED=false
STUDY_BUDDY_PROVIDER=
STUDY_BUDDY_MODEL=
STUDY_BUDDY_API_KEY=
```

Build and release commands:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
gunicorn libtrack.wsgi:application --bind 0.0.0.0:8000
```

`settings.py` raises an error at startup if `DJANGO_DEBUG` is false while
`DJANGO_SECRET_KEY` is still the development default, so a misconfigured
deployment fails loudly instead of running insecurely.

### Vercel limitations — please read

The current Vercel deployment serves the Django app through its Python runtime
and **cannot run a MySQL server**. It also has a read-only, ephemeral
filesystem. Two consequences:

1. **No MySQL on Vercel.** You must point `MYSQL_HOST` at an externally hosted
   MySQL server (PlanetScale, Aiven, Railway, Amazon RDS, or a college server).
2. **Uploaded media does not persist on Vercel.** Cover images and uploaded
   materials are written to the local filesystem, which is wiped on every
   redeploy. For a real deployment, point `DJANGO_MEDIA_ROOT` at object storage
   (S3-compatible) or a persistent volume.

**This has deliberately not been faked.** No SQLite or in-memory stand-in was
substituted to make the deployment look green. The MySQL path is fully
implemented and the only outstanding step is supplying real MySQL credentials
in the deployment environment.

Note that the previous Vercel deployment was a static front-end. This Django +
MySQL build is the new application; deploy it to a host that supports both
(a VPS, Railway, Render, or PythonAnywhere all work well for a college
project) and keep the Vercel URL for the front-end reference if you wish.

---

## 12. Assumptions and design decisions

1. **Physical copies, not a counter.** `total_copies` and `available_copies`
   are derived from `BookCopy` rows rather than stored as columns on `Book`.
   This keeps the data in third normal form and makes it structurally
   impossible for availability to drift or go negative.
2. **One borrow record.** The earlier `Reservation` model was folded into
   `Loan` with a `REQUESTED` status, so there is a single table for every
   borrowing event rather than two competing concepts.
3. **A title with history is retired, not deleted.** Deleting it would destroy
   the meaning of past loans, so the librarian's delete action sets
   `is_active = False` when any loan exists.
4. **Staff accounts have no student profile.** A librarian signs in to
   `/librarian/`, a student to `/student/`.
5. **Cover artwork is deterministic.** Books have no uploaded cover in the seed
   data, so one of the four designed cover treatments is chosen from a hash of
   the slug. This is presentation only and is not stored in the database.
6. **Deactivation is a flag, not a delete.** `StudentProfile.is_active` and
   `User.is_active` are switched off, keeping all borrowing history intact.
7. **Fine calculation** is a flat ₹10 per overdue day, applied when a book is
   returned. It is a simple demonstration rule, configurable in `services.py`.
8. **Academic structure is provisional until confirmed.** The curriculum seed
   follows the 2023–2026 NEP research handoff, but scheme, subjects and
   mappings all carry confidence fields and the scheme row is labelled
   explicitly. When the student's official timetable arrives, the CSV is
   corrected and re-imported — the import updates in place and never
   duplicates.
9. **Elective choice is browseable, not assumed.** Cloud Computing and
   Business Intelligence (Semester V) and the Semester VI electives are
   modelled as mapped subjects with "elective" classification so any student
   can browse their real reading list once the timetable is known; LibTrack
   does not claim which elective a student takes.
10. **Cover artwork is generated, not sourced.** Every title gets original,
    deterministic, text-free SVG artwork from the subject-family system
    (docs/COVER_ART.md); uploaded librarian covers still take precedence.

---

## 13. Viva notes

**Primary key.** Every table has an `id` integer column, generated by the
database. It uniquely identifies a row, is fast to index, and is never reused,
so it stays a valid reference even after a row is deleted.

**Foreign key.** A column in one table that points to the primary key of
another. `core_loan.student_id` points at `core_studentprofile.id`, so every
loan is permanently attached to exactly one student and the database rejects a
loan that points at a student who does not exist.

**Relationships.**
- *One-to-many*: one book has many copies; one student has many loans.
- *Many-to-many*: a book has many authors and a book belongs to many
  categories, so Django creates a junction table for each.
- *One-to-one*: each `StudentProfile` belongs to exactly one `User`.

**Normalization.** The schema is in 3NF. 1NF: every column holds a single
value, so authors are rows rather than a comma-separated list. 2NF: no column
depends on only part of a composite key. 3NF: no non-key column depends on
another non-key column, so each fact is stored once. The one place we could
have denormalized — a cached `available_copies` counter — is deliberately not
done, because it would create a second source of truth that could disagree
with the copy records.

**CRUD.** Create: the librarian adds a book and its copies. Read: search,
filters, pagination and reports query the database. Update: editing a title,
changing a copy's status, issuing, renewing and returning. Delete: a title with
no history is removed; one with history is retired so the records survive.

**Transactions.** Issuing and returning must be all-or-nothing. If a book is
issued and the copy is not marked on loan, the two facts would disagree.
`borrow_book` and `return_book` are wrapped in `@transaction.atomic` and lock
the row with `select_for_update()`, so two simultaneous requests cannot lend
the same physical copy. Any failure rolls the whole operation back.

**Validation.** Four layers: HTML5 attributes for immediate feedback, Django
forms for friendly messages, the service layer for business rules that depend
on current database state, and database `CHECK` / `UNIQUE` constraints as the
final guarantee.

**Authentication.** LibTrack uses Django's built-in `User` model. Passwords are
hashed with PBKDF2 and a random salt, so they cannot be read even by an
administrator. Sessions identify a logged-in user, `login_required` protects
the student and staff views, role checks separate students from librarians, and
CSRF tokens protect every form. Password strength is enforced by Django's
validator set.

**Why deleting a student is conditional.** Deleting a `StudentProfile` does not
delete the login behind it, because a `OneToOneField`'s `CASCADE` only flows
from the parent to the child, never back up. So the view deletes the `User` and
lets Django cascade down to the profile, its reading lists and its reviews.
`core_loan.student_id` is declared `PROTECT`, so a student with any loan
history aborts the delete and the view falls back to deactivation instead.
Deactivation is the correct outcome anyway: it blocks login and borrowing while
keeping the history that makes past reports meaningful.

**Why every mutating route is POST-only.** If a "delete student" link can be
followed by a `GET`, then a link prefetcher, a crawler or a stray `<img>` tag
can delete data without the user intending to. Every state-changing view is
decorated with `@require_POST` and carries a CSRF token, so a `GET` returns
405 and a cross-site POST is rejected.

**Where the numbers come from.** No dashboard figure is typed into a template.
`services.librarian_dashboard_data()` and `services.librarian_report_data()`
build every counter with `Count` / `Sum` / `Avg` aggregate queries, so the
dashboard is a live view of the database rather than a cached copy that can
drift. The same applies to `Book.available_copies`, which is a property
computed from the `BookCopy` rows rather than a stored counter.
