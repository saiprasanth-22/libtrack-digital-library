"""Tests for the scheme-aware academic layer.

Covers model constraints, catalogue filtering, the import command, librarian
permission boundaries, and the Study Buddy foundation.
"""

from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError, transaction as db_transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from core import services, study_buddy
from core.models import (Author, Book, BookCopy, BookSubjectMapping, Course,
                         CurriculumScheme, DigitalMaterial, Loan, Semester,
                         StudentProfile, Subject)
from core.tests.factories import make_book, make_student

from unittest import mock


def make_scheme(code="SCHEME-T", years=(2023, 2026)):
    course, _ = Course.objects.get_or_create(
        code="TBCA", defaults={"name": "Test BCA", "duration_semesters": 6})
    # A course may not have two schemes covering the same academic years, so
    # each test scheme gets its own distinct window.
    scheme, _ = CurriculumScheme.objects.get_or_create(
        code=code, defaults={
            "course": course, "name": f"Test scheme {code}",
            "university": "Test University",
            "academic_year_from": years[0], "academic_year_to": years[1],
        })
    return course, scheme


def make_semester(scheme, number):
    semester, _ = Semester.objects.get_or_create(
        curriculum_scheme=scheme, number=number,
        defaults={"display_name": f"Semester {number}"})
    return semester


def make_subject(semester, code, name="Test Subject", classification="core",
                 confidence="curriculum_supported", **kwargs):
    subject, _ = Subject.objects.get_or_create(
        semester=semester, code=code,
        defaults={"name": name, "classification": classification,
                  "confidence": confidence, **kwargs})
    return subject


class AcademicModelTests(TestCase):
    def setUp(self):
        self.course, self.scheme = make_scheme()
        self.semester = make_semester(self.scheme, 5)

    def test_course_duration_bounds(self):
        from django.core.exceptions import ValidationError
        course = Course(name="Odd", code="ODD", duration_semesters=13)
        with self.assertRaises(ValidationError):
            course.full_clean()
        # And the database itself refuses an out-of-range duration.
        with self.assertRaises(IntegrityError):
            with db_transaction.atomic():
                Course.objects.create(name="Odd2", code="ODD2", duration_semesters=99)

    def test_semester_unique_per_scheme(self):
        make_semester(self.scheme, 5)
        with self.assertRaises(IntegrityError):
            Semester.objects.create(curriculum_scheme=self.scheme, number=5)

    def test_subject_code_unique_within_semester(self):
        make_subject(self.semester, "X01")
        with self.assertRaises(IntegrityError):
            Subject.objects.create(semester=self.semester, code="X01", name="Second")

    def test_scheme_subject_requires_code(self):
        with self.assertRaises(IntegrityError):
            Subject.objects.create(semester=self.semester, code=None, name="NoCode")

    def test_scheme_years_ordered(self):
        bad = CurriculumScheme(course=self.course, code="BAD", name="Bad",
                               academic_year_from=2026, academic_year_to=2023)
        with self.assertRaises(IntegrityError):
            bad.save()

    def test_standalone_subject_survives(self):
        legacy, _ = Subject.objects.get_or_create(name="Standalone")
        self.assertIsNone(legacy.semester)
        legacy.full_clean()

    def test_mapping_unique_book_subject(self):
        subject = make_subject(self.semester, "X02")
        book = make_book()
        BookSubjectMapping.objects.create(book=book, subject=subject)
        with self.assertRaises(IntegrityError):
            BookSubjectMapping.objects.create(book=book, subject=subject)

    def test_book_maps_to_multiple_subjects(self):
        s1 = make_subject(self.semester, "X03")
        s2 = make_subject(make_semester(self.scheme, 6), "X04")
        book = make_book()
        BookSubjectMapping.objects.create(book=book, subject=s1)
        BookSubjectMapping.objects.create(book=book, subject=s2)
        self.assertEqual(book.subject_mappings.count(), 2)

    def test_subject_protect_blocks_delete_with_books(self):
        subject = make_subject(self.semester, "X05")
        book = make_book()
        BookSubjectMapping.objects.create(book=book, subject=subject)
        from django.db.models import ProtectedError
        with self.assertRaises(ProtectedError):
            subject.delete()

    def test_scheme_separation_same_code_different_scheme(self):
        other_course, other_scheme = make_scheme(code="SCHEME-O", years=(2024, 2027))
        other_sem = make_semester(other_scheme, 5)
        make_subject(self.semester, "SHARED")
        twin = Subject.objects.create(semester=other_sem, code="SHARED", name="Twin")
        self.assertEqual(twin.code, "SHARED")


class CatalogueFilterTests(TestCase):
    def setUp(self):
        self.course, self.scheme = make_scheme()
        self.sem5 = make_semester(self.scheme, 5)
        self.sem6 = make_semester(self.scheme, 6)
        self.r_subject = make_subject(self.sem5, "R01", "Statistical Computing")
        self.ai_subject = make_subject(self.sem6, "A01", "Machine Learning",
                                       classification="elective")
        self.r_book = make_book(title="R for Data Science", copies=2)
        self.ai_book = make_book(title="Hands-On Machine Learning", copies=1)
        BookSubjectMapping.objects.create(
            book=self.r_book, subject=self.r_subject,
            recommendation_status="recommended", resource_type="textbook")
        BookSubjectMapping.objects.create(
            book=self.ai_book, subject=self.ai_subject,
            recommendation_status="supplementary", resource_type="reference")
        self.client = Client()

    def _get(self, **params):
        return self.client.get(reverse("core:discover"), params)

    def test_filter_by_semester(self):
        response = self._get(semester=self.sem5.pk)
        titles = {b.title for b in response.context["books"]}
        self.assertIn(self.r_book.title, titles)
        self.assertNotIn(self.ai_book.title, titles)

    def test_filter_by_subject(self):
        response = self._get(subject=self.ai_subject.pk)
        titles = {b.title for b in response.context["books"]}
        self.assertEqual(titles, {self.ai_book.title})

    def test_filter_by_classification(self):
        response = self._get(classification="elective")
        titles = {b.title for b in response.context["books"]}
        self.assertEqual(titles, {self.ai_book.title})

    def test_filter_by_resource_type(self):
        response = self._get(resource_type="reference")
        titles = {b.title for b in response.context["books"]}
        self.assertIn(self.ai_book.title, titles)
        self.assertNotIn(self.r_book.title, titles)

    def test_filter_by_recommendation(self):
        response = self._get(recommendation="supplementary")
        titles = {b.title for b in response.context["books"]}
        self.assertEqual(titles, {self.ai_book.title})

    def test_combined_filters(self):
        response = self._get(course=self.course.pk, semester=self.sem5.pk,
                             subject=self.r_subject.pk, recommendation="recommended")
        self.assertEqual(response.status_code, 200)
        titles = {b.title for b in response.context["books"]}
        self.assertEqual(titles, {self.r_book.title})

    def test_search_covers_subject_and_code(self):
        response = self._get(q="Statistical")
        titles = {b.title for b in response.context["books"]}
        self.assertIn(self.r_book.title, titles)

    def test_empty_results_state(self):
        response = self._get(q="zzzznothing")
        self.assertContains(response, "No titles matched")

    def test_filters_preserved_in_pagination_links(self):
        for index in range(1, 16):
            book = make_book(title=f"Padding {index}")
            BookSubjectMapping.objects.create(book=book, subject=self.r_subject)
        response = self._get(semester=self.sem5.pk, page=1)
        self.assertContains(response, f"semester={self.sem5.pk}")

    def test_query_count_constant_across_book_volume(self):
        """Guard against N+1 on the academic card line."""
        for index in range(12):
            book = make_book(title=f"Bulk {index}")
            BookSubjectMapping.objects.create(book=book, subject=self.r_subject)

        from django.test.utils import CaptureQueriesContext
        from django.db import connection
        with CaptureQueriesContext(connection) as ctx:
            self._get(semester=self.sem5.pk)
        baseline = len(ctx)

        for index in range(20, 40):
            book = make_book(title=f"Bulk2 {index}")
            BookSubjectMapping.objects.create(book=book, subject=self.r_subject)
        with CaptureQueriesContext(connection) as ctx2:
            self._get(semester=self.sem5.pk)
        self.assertLessEqual(len(ctx2), baseline + 2)


class ImportCommandTests(TestCase):
    """Exercises the real command against a temp CSV directory."""

    def setUp(self):
        import shutil
        import tempfile
        from pathlib import Path
        self.tmp = Path(tempfile.mkdtemp())
        src = Path(__file__).resolve().parent.parent.parent / "data" / "bca"
        for name in ("courses.csv", "curriculum_schemes.csv", "semesters.csv",
                     "subjects.csv", "authors.csv", "books.csv",
                     "book_subject_mappings.csv", "digital_materials.csv"):
            shutil.copy(src / name, self.tmp / name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _run(self, *args):
        out = StringIO()
        call_command("import_bca_catalogue", *args, stdout=out)
        return out.getvalue()

    def test_first_import_creates_rows(self):
        self._run("--source", str(self.tmp))
        self.assertGreater(Book.objects.count(), 100)
        self.assertGreater(BookSubjectMapping.objects.count(), 100)
        self.assertGreaterEqual(Semester.objects.count(), 6)
        self.assertGreaterEqual(Course.objects.count(), 1)

    def test_second_import_is_idempotent(self):
        self._run("--source", str(self.tmp))
        before = (Book.objects.count(), Author.objects.count(),
                  BookSubjectMapping.objects.count())
        output = self._run("--source", str(self.tmp))
        after = (Book.objects.count(), Author.objects.count(),
                 BookSubjectMapping.objects.count())
        self.assertEqual(before, after)
        self.assertIn("Import finished with no invalid rows", output)

    def test_dry_run_writes_nothing(self):
        self._run("--dry-run", "--source", str(self.tmp))
        self.assertEqual(Book.objects.filter(cover_family="").count()
                         + Book.objects.exclude(cover_family="").count(), 0)

    def test_dry_run_rollback_on_crash(self):
        """A crash mid-import must leave every table untouched.

        ``BookCopy.objects.create`` is detonated: by the time the first book's
        copies are created, the importer has already written courses, schemes,
        semesters, subjects, authors and at least one book row - so the
        assertions below prove those writes were rolled back, not merely that
        nothing had happened yet.
        """
        with mock.patch("core.models.BookCopy.objects.create",
                        side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self._run("--dry-run", "--source", str(self.tmp))
        self.assertEqual(Course.objects.count(), 0)
        self.assertEqual(CurriculumScheme.objects.count(), 0)
        self.assertEqual(Semester.objects.count(), 0)
        self.assertEqual(Subject.objects.count(), 0)
        self.assertEqual(Author.objects.count(), 0)
        self.assertEqual(Book.objects.count(), 0)
        self.assertEqual(BookCopy.objects.count(), 0)

    def test_strict_rollback_on_invalid_row(self):
        from pathlib import Path
        # Corrupt the books file with a row missing an author.
        books_path = self.tmp / "books.csv"
        text = books_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        lines.append("broken-row-slug,Broken Book,,McGraw Hill,2020,1st,,English,300,Broken,Cyber Security,cybersecurity,1,CY-X1,false")
        books_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with self.assertRaises(Exception):
            self._run("--strict", "--source", str(self.tmp))
        self.assertEqual(Book.objects.filter(title="Broken Book").count(), 0)

    def test_duplicate_isbn_conflict_reported(self):
        from pathlib import Path
        books_path = self.tmp / "books.csv"
        text = books_path.read_text(encoding="utf-8")
        # Re-use an existing ISBN under a new slug.
        first = text.splitlines()[1]
        parts = first.split(",")
        isbn = parts[7]
        books_path.write_text(
            text + f'conflict-slug,Conflict Book,,Some Author,P,2020,1st,{isbn},English,100,Dup,X,cybersecurity,1,CY-X2,false\n',
            encoding="utf-8")
        output = self._run("--source", str(self.tmp))
        self.assertIn("invalid", output)
        self.assertFalse(Book.objects.filter(slug="conflict-slug").exists())

    def test_multiple_blank_isbns_allowed(self):
        self._run("--source", str(self.tmp))
        blank = Book.objects.filter(isbn__isnull=True) | Book.objects.filter(isbn="")
        self.assertGreater(blank.count(), 20)

    def test_copies_created_to_requested_count(self):
        """Exact copy counts from the CSV, and a re-import adds none."""
        self._run("--source", str(self.tmp))
        # The test database starts empty, so counts must match the CSV exactly.
        self.assertEqual(
            BookCopy.objects.filter(book__slug="programming-in-ansi-c").count(), 5)
        self.assertEqual(
            BookCopy.objects.filter(book__slug="php-manual-companion").count(), 1)
        total_after_first = BookCopy.objects.count()

        # Second import: copies must be recognised, never duplicated.
        output = self._run("--source", str(self.tmp))
        self.assertEqual(
            BookCopy.objects.filter(book__slug="programming-in-ansi-c").count(), 5)
        self.assertEqual(BookCopy.objects.count(), total_after_first)
        self.assertIn("copies", output)

    def test_author_names_split_on_semicolon(self):
        self._run("--source", str(self.tmp))
        book = Book.objects.get(slug="database-system-concepts")
        names = set(book.authors.values_list("name", flat=True))
        self.assertIn("Abraham Silberschatz", names)
        self.assertEqual(len(names), 3)


class LibrarianPermissionTests(TestCase):
    def setUp(self):
        self.course, self.scheme = make_scheme()
        self.semester = make_semester(self.scheme, 5)
        self.subject = make_subject(self.semester, "P01")
        self.student, _ = make_student(username="perm.student")
        self.librarian = User.objects.create_user(
            username="perm.librarian", password="test-pass-4321", is_staff=True)
        self.client = Client()

    # ``make_student`` returns (user, profile); the user is the login object.

    def test_anonymous_redirected_from_academics(self):
        response = self.client.get(reverse("core:librarian_academics"))
        self.assertEqual(response.status_code, 302)

    def test_student_forbidden_from_academics(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("core:librarian_academics"))
        self.assertEqual(response.status_code, 302)

    def test_librarian_sees_academics(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("core:librarian_academics"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Academic management")

    def test_librarian_sees_subject_detail(self):
        self.client.force_login(self.librarian)
        response = self.client.get(reverse("core:librarian_subject_detail",
                                           args=[self.subject.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.subject.name)

    def test_mapping_create_via_post(self):
        book = make_book(title="Mapped title")
        self.client.force_login(self.librarian)
        response = self.client.post(
            reverse("core:librarian_subject_detail", args=[self.subject.pk]),
            {"action": "map", "book": str(book.pk),
             "resource_type": "textbook", "recommendation_status": "recommended"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(BookSubjectMapping.objects.filter(book=book, subject=self.subject).exists())

    def test_mapping_delete_via_post(self):
        book = make_book(title="Unmapped title")
        mapping = BookSubjectMapping.objects.create(book=book, subject=self.subject)
        self.client.force_login(self.librarian)
        response = self.client.post(
            reverse("core:librarian_subject_detail", args=[self.subject.pk]),
            {"action": "unmap", "mapping": str(mapping.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BookSubjectMapping.objects.filter(pk=mapping.pk).exists())

    def test_student_cannot_mutate_mappings(self):
        book = make_book(title="Student attempt")
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("core:librarian_subject_detail", args=[self.subject.pk]),
            {"action": "map", "book": str(book.pk)})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(BookSubjectMapping.objects.filter(book=book).exists())

    def test_get_cannot_map(self):
        book = make_book(title="GET attempt")
        self.client.force_login(self.librarian)
        response = self.client.get(
            reverse("core:librarian_subject_detail", args=[self.subject.pk]),
            {"action": "map", "book": str(book.pk)})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(BookSubjectMapping.objects.filter(book=book).exists())


class BookDetailAcademicTests(TestCase):
    def setUp(self):
        self.course, self.scheme = make_scheme()
        self.semester = make_semester(self.scheme, 5)
        self.subject = make_subject(self.semester, "D01", "Design and Analysis of Algorithms")
        self.client = Client()

    def test_academic_tab_renders_mappings(self):
        book = make_book(title="Algorithms illustrated")
        BookSubjectMapping.objects.create(
            book=book, subject=self.subject,
            recommendation_status="recommended",
            syllabus_note="Supports the design-strategies unit")
        response = self.client.get(
            reverse("core:book_detail", args=[book.slug]))
        self.assertContains(response, "Academic relevance")
        self.assertContains(response, self.subject.code)
        self.assertContains(response, "Supports the design-strategies unit")

    def test_unmapped_book_shows_truthful_empty_state(self):
        book = make_book(title="General interest only")
        response = self.client.get(
            reverse("core:book_detail", args=[book.slug]))
        self.assertContains(response, "not yet mapped")

    def test_multiple_subjects_render(self):
        book = make_book(title="Shared between papers")
        other = make_subject(make_semester(self.scheme, 6), "D02", "Second subject")
        BookSubjectMapping.objects.create(book=book, subject=self.subject)
        BookSubjectMapping.objects.create(book=book, subject=other)
        response = self.client.get(reverse("core:book_detail", args=[book.slug]))
        self.assertContains(response, self.subject.code)
        self.assertContains(response, other.code)

    def test_no_missing_author_concealment(self):
        book = make_book(title="Authorless display", authors=())
        response = self.client.get(reverse("core:book_detail", args=[book.slug]))
        # The legacy fallback string must not paper over a real gap.
        self.assertNotContains(response, "LibTrack Collection")


class StudyBuddyTests(TestCase):
    def setUp(self):
        self.student, self.profile = make_student(username="buddy.user")
        self.client = Client()

    def test_disabled_by_default(self):
        from django.conf import settings as dj
        if not dj.STUDY_BUDDY_ENABLED:
            self.assertFalse(study_buddy.is_configured())
        response = self.client.get(reverse("core:study_buddy"))
        # Not authenticated: redirected to login.
        self.assertEqual(response.status_code, 302)

    def test_fully_configured_reports_ready(self):
        from django.test import override_settings as ovr
        with ovr(STUDY_BUDDY_ENABLED=True, STUDY_BUDDY_PROVIDER="echo",
                 STUDY_BUDDY_MODEL="test-model", STUDY_BUDDY_API_KEY="test-key"):
            self.assertTrue(study_buddy.is_configured())
            provider = study_buddy.get_provider()
            self.assertEqual(provider.name, "echo")

    def test_page_renders_disabled_state(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("core:study_buddy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Awaiting configuration")
        self.assertContains(response, "STUDY_BUDDY_ENABLED")

    def test_librarian_gets_login_redirect(self):
        librarian = User.objects.create_user(
            username="buddy.librarian", password="test-pass-4321", is_staff=True)
        self.client.force_login(librarian)
        response = self.client.get(reverse("core:study_buddy"))
        self.assertEqual(response.status_code, 302)

    def test_provider_raises_while_unconfigured(self):
        with self.assertRaises(study_buddy.StudyBuddyUnavailable):
            study_buddy.get_provider()

    def test_prompt_contains_academic_context(self):
        provider = study_buddy.EchoProvider()
        context = study_buddy.StudyContext(
            course_name="BCA", semester=5,
            subject_name="Statistical Computing", subject_code="DCCAS02",
            book_title="The Book of R", chapter_topic="Hypothesis testing",
            mode="viva", question="What is a p-value?")
        result = provider.generate_response(context)
        for token in ("BCA", "Semester: 5", "DCCAS02", "The Book of R",
                      "Hypothesis testing", "What is a p-value?"):
            self.assertIn(token, result.text)

    def test_input_limit_enforced(self):
        from django.test import override_settings as ovr
        with ovr(STUDY_BUDDY_MAX_INPUT_CHARS=10):
            prompt = study_buddy.build_prompt(
                study_buddy.StudyContext(question="x" * 500))
        self.assertLessEqual(len(prompt.split("Question: ")[1]), 10)

    def test_no_secret_in_template_context(self):
        from django.test import override_settings as ovr
        with ovr(STUDY_BUDDY_ENABLED=True, STUDY_BUDDY_PROVIDER="echo",
                 STUDY_BUDDY_MODEL="test-model",
                 STUDY_BUDDY_API_KEY="super-secret-key-value"):
            self.client.force_login(self.student)
            response = self.client.get(reverse("core:study_buddy"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("super-secret-key-value", response.content.decode())
