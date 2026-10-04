# LibTrack

LibTrack is a premium digital library management platform for college students and librarians. It uses Django, Django Templates, modern CSS/JavaScript, and a MySQL-ready database configuration.

## Current state

- Production-quality responsive landing page
- Interactive five-stage Platform Tour
- Vercel deployment configuration through native Django detection
- SQLite fallback for local development
- MySQL configuration through environment variables

Production: https://libtrack-digital-library.vercel.app

## Local setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
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

Planned implementation order:

1. Database models and seed data
2. Authentication and role separation
3. Discover and global search
4. Book details and availability
5. Student dashboard
6. Librarian dashboard
7. Borrowing, reservations, reports, and final QA

## Collaboration

- Create a feature branch for each unit of work.
- Keep reusable layout pieces in Django template partials.
- Preserve the existing design tokens and typography hierarchy.
- Run `python manage.py check` before opening a pull request.
