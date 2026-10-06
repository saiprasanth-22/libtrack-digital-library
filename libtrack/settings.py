"""Django settings for the LibTrack digital library project.

Configuration is environment driven so the same code runs locally (SQLite
fallback) and against a real MySQL server. No secret is ever committed:
every sensitive value is read from an environment variable and falls back to a
clearly-marked development default.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    """Read a boolean flag from the environment."""
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=()):
    """Read a comma separated list from the environment."""
    raw = os.getenv(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()] or list(default)


# --------------------------------------------------------------------------
# Core security
# --------------------------------------------------------------------------

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-libtrack-insecure-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "[::1]"])
ALLOWED_HOSTS += [".vercel.app"]

# The development fallback secret must never reach a real deployment.
if not DEBUG and SECRET_KEY == "dev-only-libtrack-insecure-secret-key":
    raise RuntimeError(
        "DJANGO_SECRET_KEY must be set to a unique value when DJANGO_DEBUG is false."
    )

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "libtrack.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "core.context_processors.library_rules",
    ]},
}]
WSGI_APPLICATION = "libtrack.wsgi.application"
ASGI_APPLICATION = "libtrack.asgi.application"

# --------------------------------------------------------------------------
# Database - MySQL is the target runtime database; SQLite is a local fallback
# so the project can be demonstrated on a machine without a MySQL server.
# --------------------------------------------------------------------------

if os.getenv("MYSQL_DATABASE"):
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.getenv("MYSQL_DATABASE"),
        "USER": os.getenv("MYSQL_USER"),
        "PASSWORD": os.getenv("MYSQL_PASSWORD"),
        "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
        "PORT": os.getenv("MYSQL_PORT", "3306"),
        "CONN_MAX_AGE": int(os.getenv("MYSQL_CONN_MAX_AGE", "60")),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20},
    }}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --------------------------------------------------------------------------
# Authentication
# --------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "core:portal_select"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:home"
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "0"))
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# --------------------------------------------------------------------------
# Internationalisation
# --------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DJANGO_TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------------------
# Static and media files
# --------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("DJANGO_MEDIA_ROOT", BASE_DIR / "media"))

# The hashed manifest storage is always configured so that `collectstatic`
# always writes a manifest, whatever DJANGO_DEBUG happens to be at the time.
# Otherwise running `collectstatic` locally and then serving with
# DJANGO_DEBUG=false would fail with "Missing staticfiles manifest entry".
# While DEBUG is on, Django's `{% static %}` tag bypasses the manifest, so
# development is unaffected. The test suite swaps in a plain backend via
# LibTrackTestRunner, because it has no collectstatic step.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

TEST_RUNNER = "core.test_runner.LibTrackTestRunner"

WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30 if not DEBUG else 0

# --------------------------------------------------------------------------
# Library business rules
#
# Every limit used by the circulation logic lives here so the numbers are
# configurable instead of scattered through the views and services.
# --------------------------------------------------------------------------

LIBRARY_RULES = {
    # How long a freshly issued book stays with the student.
    "LOAN_DAYS": int(os.getenv("LIBRARY_LOAN_DAYS", "14")),
    # Maximum number of books a student may hold at one time.
    "MAX_ACTIVE_LOANS": int(os.getenv("LIBRARY_MAX_ACTIVE_LOANS", "3")),
    # How many times a loan may be extended.
    "MAX_RENEWALS": int(os.getenv("LIBRARY_MAX_RENEWALS", "1")),
    # Extra days granted by one renewal.
    "RENEWAL_DAYS": int(os.getenv("LIBRARY_RENEWAL_DAYS", "7")),
    # Window used by the dashboard "due soon" counters.
    "DUE_SOON_DAYS": int(os.getenv("LIBRARY_DUE_SOON_DAYS", "7")),
    # Books shown per catalogue page.
    "PAGE_SIZE": int(os.getenv("LIBRARY_PAGE_SIZE", "12")),
}

LIBRARY_COVER_VARIANTS = ("architecture", "topography", "grid", "orbital")

# --------------------------------------------------------------------------
# Study Buddy (optional AI study companion)
#
# The feature stays disabled until every marked variable is configured. No
# network call is possible while STUDY_BUDDY_ENABLED is false, and the API
# key is only ever read server-side by the provider adapter.
# --------------------------------------------------------------------------

STUDY_BUDDY_ENABLED = env_bool("STUDY_BUDDY_ENABLED", False)
STUDY_BUDDY_PROVIDER = os.getenv("STUDY_BUDDY_PROVIDER", "")
STUDY_BUDDY_MODEL = os.getenv("STUDY_BUDDY_MODEL", "")
STUDY_BUDDY_API_KEY = os.getenv("STUDY_BUDDY_API_KEY", "")
STUDY_BUDDY_MAX_INPUT_CHARS = int(os.getenv("STUDY_BUDDY_MAX_INPUT_CHARS", "4000"))
STUDY_BUDDY_DAILY_LIMIT = int(os.getenv("STUDY_BUDDY_DAILY_LIMIT", "20"))

# --------------------------------------------------------------------------
# Uploads
# --------------------------------------------------------------------------

DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
