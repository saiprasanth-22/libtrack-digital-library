"""Import the BCA academic catalogue from the CSV files in ``data/bca/``.

The command is idempotent: every row is looked up by a natural key before it
is created, and re-running with the same data reports everything as
``unchanged`` instead of duplicating. Failures are reported row by row, and
``--strict`` wraps the whole run in one transaction so a failed import rolls
back completely.

    python manage.py import_bca_catalogue
    python manage.py import_bca_catalogue --dry-run
    python manage.py import_bca_catalogue --strict
    python manage.py import_bca_catalogue --source data/bca
"""

import csv
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import (Author, Book, BookCopy, BookSubjectMapping, Category,
                         Course, CurriculumScheme, DigitalMaterial, Semester,
                         Subject)

INSTITUTIONAL_AUTHOR = "LibTrack Academic Desk"


def read_csv(path):
    """Read one CSV file, returning a list of dicts."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [row for row in csv.DictReader(handle)
                if any((value or "").strip() for value in row.values())]


class Command(BaseCommand):
    help = "Import the BCA academic catalogue from data/bca CSV files."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="data/bca",
                            help="Directory holding the catalogue CSV files.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Validate and report without writing anything.")
        parser.add_argument("--strict", action="store_true",
                            help="Abort and roll back on the first error.")

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tally = {}

    def tally_key(self, kind, outcome):
        self.tally.setdefault(kind, {"created": 0, "updated": 0, "unchanged": 0,
                                     "skipped": 0, "invalid": 0})
        self.tally[kind][outcome] += 1

    def report(self):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Import summary"))
        for kind, counts in self.tally.items():
            parts = [f"{outcome}: {count}" for outcome, count in counts.items()
                     if count or outcome in ("created", "unchanged")]
            self.stdout.write(f"  {kind:<18} " + ", ".join(parts))
        invalid = sum(counts["invalid"] for counts in self.tally.values())
        if invalid:
            self.stdout.write(self.style.WARNING(f"\n{invalid} invalid row(s) were skipped."))
        else:
            self.stdout.write(self.style.SUCCESS("\nImport finished with no invalid rows."))

    # ------------------------------------------------------------------
    # Row helpers
    # ------------------------------------------------------------------

    def fail(self, kind, label, message):
        """Record one invalid row; raise under --strict."""
        self.tally_key(kind, "invalid")
        self.stdout.write(self.style.ERROR(f"  [{kind}] {label}: {message}"))
        if self.strict:
            raise CommandError(f"Strict import aborted at {kind}: {label} - {message}")

    def text(self, row, field, default=""):
        value = (row.get(field) or "").strip()
        return value or default

    def boolean(self, row, field, default=True):
        raw = (row.get(field) or "").strip().lower()
        if not raw:
            return default
        return raw in {"1", "true", "yes", "on"}

    def integer(self, row, field):
        raw = (row.get(field) or "").strip()
        return int(raw) if raw else None

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.strict = options["strict"]
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
        self.source = Path(options["source"])
        if not self.source.is_absolute():
            self.source = Path.cwd() / self.source

        courses = read_csv(self.source / "courses.csv")
        schemes = read_csv(self.source / "curriculum_schemes.csv")
        semesters = read_csv(self.source / "semesters.csv")
        subjects = read_csv(self.source / "subjects.csv")
        authors = read_csv(self.source / "authors.csv")
        books = read_csv(self.source / "books.csv")
        mappings = read_csv(self.source / "book_subject_mappings.csv")
        materials = read_csv(self.source / "digital_materials.csv")
        if not any((courses, schemes, semesters, subjects, authors, books,
                    mappings, materials)):
            raise CommandError(f"No catalogue CSV files found in {self.source}.")

        if self.dry_run:
            self.stdout.write(self.style.NOTICE(
                "Dry run: no database changes will be written.\n"))
        else:
            self.stdout.write("Importing the academic catalogue...\n")

        try:
            if self.dry_run:
                # A dry run must never leave partial writes behind, even if it
                # crashes halfway: everything happens inside one transaction
                # that is forcibly rolled back when the work completes.
                with transaction.atomic():
                    self.import_all(courses, schemes, semesters, subjects,
                                    authors, books, mappings, materials)
                    transaction.set_rollback(True)
            elif self.strict:
                with transaction.atomic():
                    self.import_all(courses, schemes, semesters, subjects,
                                    authors, books, mappings, materials)
            else:
                self.import_all(courses, schemes, semesters, subjects,
                                authors, books, mappings, materials)
        except CommandError:
            if self.strict:
                self.stdout.write(self.style.ERROR(
                    "\nStrict import failed. All changes were rolled back."))
            raise

        self.report()

    def import_all(self, courses, schemes, semesters, subjects, authors,
                   books, mappings, materials):
        course_by_code = self.import_courses(courses)
        scheme_by_code = self.import_schemes(schemes, course_by_code)
        semester_by_key = self.import_semesters(semesters, scheme_by_code)
        subject_by_key = self.import_subjects(subjects, semester_by_key)
        self.import_authors(authors)
        book_by_slug = self.import_books(books)
        self.import_mappings(mappings, subject_by_key, book_by_slug)
        self.import_materials(materials, subject_by_key)

    # ------------------------------------------------------------------
    # Per-entity importers (each idempotent by natural key)
    # ------------------------------------------------------------------

    def import_courses(self, rows):
        by_code = {}
        for index, row in enumerate(rows, 2):
            label = row.get("code") or f"row {index}"
            code = self.text(row, "code")
            name = self.text(row, "name")
            if not code or not name:
                self.fail("course", label, "code and name are required")
                continue
            try:
                duration = int(self.text(row, "duration_semesters", "6"))
            except ValueError:
                self.fail("course", label, "duration_semesters must be a number")
                continue
            course, created = Course.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "duration_semesters": duration,
                    "description": self.text(row, "description"),
                    "is_active": self.boolean(row, "is_active"),
                })
            if created:
                self.tally_key("courses", "created")
                self.stdout.write(f"  + course {course}")
            else:
                self.merge(course, row, {
                    "name": name,
                    "duration_semesters": duration,
                    "description": self.text(row, "description"),
                    "is_active": self.boolean(row, "is_active"),
                }, "courses", str(course))
            by_code[code] = course
        return by_code

    def import_schemes(self, rows, course_by_code):
        by_code = {}
        for index, row in enumerate(rows, 2):
            label = row.get("code") or f"row {index}"
            code = self.text(row, "code")
            course = course_by_code.get(self.text(row, "course_code"))
            if not code or course is None:
                self.fail("scheme", label, "code and a known course_code are required")
                continue
            scheme, created = CurriculumScheme.objects.get_or_create(
                code=code,
                defaults={
                    "course": course,
                    "name": self.text(row, "name", code),
                    "university": self.text(row, "university"),
                    "academic_year_from": self.integer(row, "academic_year_from"),
                    "academic_year_to": self.integer(row, "academic_year_to"),
                    "verification_status": self.text(row, "verification_status",
                                                     "provisional"),
                    "source_url": self.text(row, "source_url"),
                    "notes": self.text(row, "notes"),
                    "is_active": self.boolean(row, "is_active"),
                })
            if created:
                self.tally_key("schemes", "created")
                self.stdout.write(f"  + scheme {scheme}")
            else:
                self.merge(scheme, row, {
                    "course": course,
                    "name": self.text(row, "name", code),
                    "university": self.text(row, "university"),
                    "academic_year_from": self.integer(row, "academic_year_from"),
                    "academic_year_to": self.integer(row, "academic_year_to"),
                    "verification_status": self.text(row, "verification_status",
                                                     "provisional"),
                    "source_url": self.text(row, "source_url"),
                    "notes": self.text(row, "notes"),
                    "is_active": self.boolean(row, "is_active"),
                }, "schemes", str(scheme))
            by_code[code] = scheme
        return by_code

    def import_semesters(self, rows, scheme_by_code):
        by_key = {}
        for index, row in enumerate(rows, 2):
            number = self.integer(row, "number")
            label = f"{row.get('scheme_code')}/{number}" if number else f"row {index}"
            scheme = scheme_by_code.get(self.text(row, "scheme_code"))
            if scheme is None or number is None:
                self.fail("semester", label, "scheme_code and number are required")
                continue
            semester, created = Semester.objects.get_or_create(
                curriculum_scheme=scheme, number=number,
                defaults={
                    "display_name": self.text(row, "display_name", f"Semester {number}"),
                    "is_active": self.boolean(row, "is_active"),
                })
            if created:
                self.tally_key("semesters", "created")
            else:
                self.merge(semester, row, {
                    "display_name": self.text(row, "display_name", f"Semester {number}"),
                    "is_active": self.boolean(row, "is_active"),
                }, "semesters", label)
            by_key[(scheme.code, number)] = semester
        return by_key

    def import_subjects(self, rows, semester_by_key):
        by_key = {}
        for index, row in enumerate(rows, 2):
            code = self.text(row, "code")
            label = f"{code} ({row.get('semester_number')})" if code else f"row {index}"
            key = (self.text(row, "scheme_code"), self.integer(row, "semester_number"))
            semester = semester_by_key.get(key)
            if semester is None or not code:
                self.fail("subject", label, "a known scheme/semester and a code are required")
                continue
            defaults = {
                "name": self.text(row, "name"),
                "classification": self.text(row, "classification", "core"),
                "confidence": self.text(row, "confidence", "curriculum_supported"),
                "description": self.text(row, "description"),
                "source_url": self.text(row, "source_url"),
                "is_active": self.boolean(row, "is_active"),
            }
            try:
                subject, created = Subject.objects.get_or_create(
                    semester=semester, code=code, defaults=defaults)
            except Exception as error:
                self.fail("subject", label, str(error))
                continue
            if created:
                self.tally_key("subjects", "created")
            else:
                self.merge(subject, row, defaults, "subjects", label)
            by_key[(key[0], key[1], code)] = subject
        return by_key

    def import_authors(self, rows):
        for index, row in enumerate(rows, 2):
            name = self.text(row, "name")
            if not name:
                self.fail("author", f"row {index}", "name is required")
                continue
            author, created = Author.objects.get_or_create(
                name=name, defaults={"biography": self.text(row, "biography")})
            if created:
                self.tally_key("authors", "created")
            else:
                self.merge(author, row, {"biography": self.text(row, "biography")},
                           "authors", name)

    def import_books(self, rows):
        by_slug = {}
        for index, row in enumerate(rows, 2):
            slug = self.text(row, "slug")
            title = self.text(row, "title")
            label = slug or f"row {index}"
            if not slug or not title:
                self.fail("book", label, "slug and title are required")
                continue
            author_names = [part.strip() for part in self.text(row, "authors").split(";")
                            if part.strip()]
            if not author_names:
                self.fail("book", label, "at least one author is required")
                continue
            isbn = (self.text(row, "isbn") or "").strip()
            fields = {
                "title": title,
                "subtitle": self.text(row, "subtitle"),
                "publisher": self.text(row, "publisher"),
                "publication_year": self.integer(row, "publication_year"),
                "edition": self.text(row, "edition"),
                "language": self.text(row, "language", "English"),
                "page_count": self.integer(row, "page_count"),
                "description": self.text(row, "description"),
                "cover_family": self.text(row, "cover_family"),
                "featured": self.boolean(row, "featured", False),
            }
            if isbn:
                clash = Book.objects.filter(isbn=isbn).exclude(slug=slug).first()
                if clash:
                    self.fail("book", label,
                              f"ISBN {isbn} already belongs to '{clash.slug}'")
                    continue
            try:
                book = Book.objects.filter(slug=slug).first()
                if book is None:
                    book = Book(slug=slug, **fields)
                    if isbn:
                        book.isbn = isbn
                    book.save()
                    created = True
                else:
                    created = False
                    for field, value in fields.items():
                        setattr(book, field, value)
                    if isbn:
                        book.isbn = isbn
                    book.save()
            except Exception as error:
                self.fail("book", label, str(error))
                continue
            if created:
                self.tally_key("books", "created")
                self.stdout.write(f"  + book {book.title}")
            else:
                # Idempotent update path: recompute slug-dependent fields but
                # never touch copies, loans or reviews.
                for field, value in fields.items():
                    if getattr(book, field) != value:
                        setattr(book, field, value)
                book.save()
                self.tally_key("books", "unchanged")
            for name in author_names:
                author, _ = Author.objects.get_or_create(
                    name=name, defaults={"biography": ""})
                book.authors.add(author)
            category_names = [part.strip() for part in self.text(row, "categories").split(";")
                              if part.strip()]
            for name in category_names:
                category = self.get_or_create_category(name)
                book.categories.add(category)
            self.ensure_copies(book, row, created)
            by_slug[slug] = book
        return by_slug

    def get_or_create_category(self, name):
        """Categories have a unique non-auto slug, so it is set explicitly."""
        existing = Category.objects.filter(name=name).first()
        if existing:
            return existing
        from django.utils.text import slugify
        base = slugify(name) or "category"
        candidate, suffix = base, 2
        while Category.objects.filter(slug=candidate).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return Category.objects.create(name=name, slug=candidate)

    def ensure_copies(self, book, row, created_book):
        """Top up physical copies to the requested count without shrinking."""
        wanted = self.integer(row, "copies")
        if not wanted or wanted < 1:
            return
        existing = book.copies.count()
        if existing >= wanted:
            self.tally_key("copies", "unchanged")
            return
        missing = wanted - existing
        prefix = slug_like = (book.slug or f"book-{book.pk}")[:20].upper()
        created_count = 0
        for offset in range(missing):
            for attempt in range(1, 60):
                candidate = f"{prefix}-{existing + offset + attempt:03d}"
                if not BookCopy.objects.filter(accession_number=candidate).exists():
                    BookCopy.objects.create(
                        book=book, accession_number=candidate,
                        shelf_location=self.text(row, "shelf_location"))
                    created_count += 1
                    break
            else:
                self.fail("copy", candidate, "could not allocate a free accession number")
                break
        if created_count:
            self.tally_key("copies", "created")
        self.tally_key("copies", "unchanged") if not created_count else None

    def import_mappings(self, rows, subject_by_key, book_by_slug):
        for index, row in enumerate(rows, 2):
            slug = self.text(row, "book_slug")
            code = self.text(row, "subject_code")
            label = f"{slug} -> {code}" if slug and code else f"row {index}"
            book = book_by_slug.get(slug)
            subject_key = (self.text(row, "scheme_code"),
                           self.integer(row, "semester_number"), code)
            subject = subject_by_key.get(subject_key)
            if book is None or subject is None:
                self.fail("mapping", label, "unknown book_slug or subject key")
                continue
            defaults = {
                "resource_type": self.text(row, "resource_type", "textbook"),
                "recommendation_status": self.text(row, "recommendation_status",
                                                   "recommended"),
                "syllabus_note": self.text(row, "syllabus_note"),
                "confidence": self.text(row, "confidence", "curriculum_supported"),
            }
            mapping, created = BookSubjectMapping.objects.get_or_create(
                book=book, subject=subject, defaults=defaults)
            if created:
                self.tally_key("mappings", "created")
            else:
                self.merge(mapping, row, defaults, "mappings", label)

    def import_materials(self, rows, subject_by_key):
        for index, row in enumerate(rows, 2):
            title = self.text(row, "title")
            if not title:
                self.fail("material", f"row {index}", "title is required")
                continue
            subject = subject_by_key.get(
                (self.text(row, "scheme_code"), self.integer(row, "semester_number"),
                 self.text(row, "subject_code")))
            material = DigitalMaterial.objects.filter(
                title=title, material_type=self.text(row, "material_type", "other"),
                subject=subject).first()
            if material is None:
                material = DigitalMaterial(
                    title=title,
                    material_type=self.text(row, "material_type", "other"),
                    subject=subject,
                    description=self.text(row, "description"),
                    external_url=self.text(row, "external_url"),
                    is_public=self.boolean(row, "is_public", True))
                material.save()
                self.tally_key("materials", "created")
                for name in [p.strip() for p in self.text(row, "authors").split(";")
                             if p.strip()]:
                    author, _ = Author.objects.get_or_create(name=name)
                    material.authors.add(author)
            else:
                changed = self.merge(material, row, {
                    "description": self.text(row, "description"),
                    "external_url": self.text(row, "external_url"),
                    "is_public": self.boolean(row, "is_public", True),
                }, "materials", title)
                if not changed:
                    self.tally_key("materials", "unchanged")

    def merge(self, instance, row, values, kind, label):
        """Apply CSV values onto an existing row when they differ."""
        changed = False
        for field, value in values.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed = True
        if changed:
            if self.dry_run:
                self.tally_key(kind, "updated")
                self.stdout.write(f"  ~ [{kind}] {label}: would update")
            else:
                instance.save()
                self.tally_key(kind, "updated")
                self.stdout.write(f"  ~ [{kind}] {label}: updated")
        else:
            self.tally_key(kind, "unchanged")
        return changed
