# LibTrack

LibTrack is a premium digital library management platform for college students and librarians. It uses Django, Django Templates, modern CSS/JavaScript, and a MySQL-ready database configuration.

## Current state

- Production-quality responsive landing page
- Interactive five-stage Platform Tour
- Vercel deployment configuration through native Django detection
- SQLite fallback for local development
- MySQL configuration through environment variables
- Relational catalogue, copies, students, loans, reservations, reading lists, reviews, materials, and activity records
- Transaction-safe issue, return, fine, reservation-queue, and availability services
- Student authentication and database-backed dashboard
- Staff-only catalogue, circulation, analytics, and Django administration

Production: https://libtrack-digital-library.vercel.app

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_library
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## MySQL configuration

Set these environment variables before running Django:

```text
MYSQL_DATABASE
MYSQL_USER
MYSQL_PASSWORD
MYSQL_HOST
MYSQL_PORT
DJANGO_SECRET_KEY
DJANGO_DEBUG=false
```

Without `MYSQL_DATABASE`, the project uses local SQLite.

The seed command is idempotent and creates a presentation-ready catalogue plus:

- Student: `demo.student`
- Librarian: `demo.librarian`
- Local-only default password: `LibTrackDemo2026!`

Set `LIBTRACK_DEMO_PASSWORD` before seeding any shared environment.

## Architecture

```text
core/                  Public-facing views and URLs
libtrack/              Django project settings and entry points
templates/             Django page templates
static/css/            Design system and responsive page styling
static/js/             UI interactions
```

## Product direction

The design language combines academic heritage with modern product clarity:

- Instrument Serif for editorial display typography
- Manrope for interface typography
- Ink, forest green, paper, cream, warm brown, and functional emerald
- Product-led layouts rather than generic admin dashboards

Implemented product flow:

1. Registration and authentication
2. Catalogue search and book availability
3. Borrowing, returns, reservations, and saved resources
4. Student loans and reading workspace
5. Librarian catalogue, circulation, analytics, and reports
6. MySQL-ready deployment configuration

## Collaboration

- Create a feature branch for each unit of work.
- Keep reusable layout pieces in Django template partials.
- Preserve the existing design tokens and typography hierarchy.
- Run `python manage.py check` before opening a pull request.
