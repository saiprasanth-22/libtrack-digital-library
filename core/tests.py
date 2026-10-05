from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    ActivityLog,
    Author,
    Book,
    BookCopy,
    Loan,
    ReadingList,
    Reservation,
    SavedResource,
    StudentProfile,
)


User = get_user_model()


class LibTrackFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student_user = User.objects.create_user(
            username="mira", password="correct-horse-123", first_name="Mira", email="mira@example.test"
        )
        cls.student = StudentProfile.objects.create(
            user=cls.student_user, student_id="STU-1001", department="Computer Science"
        )
        cls.reading_list = ReadingList.objects.create(
            student=cls.student, name="My reading list", is_default=True
        )
        cls.staff_user = User.objects.create_user(
            username="librarian", password="staff-password-123", is_staff=True
        )
        cls.author = Author.objects.create(name="A. Silberschatz")
        cls.book = Book.objects.create(
            title="Database System Concepts", isbn="9780078022159", description="DBMS foundations"
        )
        cls.book.authors.add(cls.author)
        cls.copy = BookCopy.objects.create(book=cls.book, accession_number="LIB-DB-001")

    def test_student_and_librarian_views_require_authentication(self):
        for route in ("core:student", "core:librarian", "core:librarian_catalogue"):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("core:login"), response["Location"])

    def test_student_login_reaches_database_backed_dashboard(self):
        response = self.client.post(reverse("core:login"), {
            "username": "mira", "password": "correct-horse-123",
        })
        self.assertRedirects(response, reverse("core:student"))
        dashboard = self.client.get(reverse("core:student"))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Database System Concepts")
        self.assertContains(dashboard, "STU-1001")

    def test_registration_creates_student_profile_and_default_reading_list(self):
        response = self.client.post(reverse("core:register"), {
            "first_name": "Asha", "last_name": "Rao", "student_id": "STU-2002",
            "department": "Physics", "email": "asha@example.test", "username": "asha",
            "password": "secure-password-123", "password_confirm": "secure-password-123",
        })
        self.assertRedirects(response, reverse("core:student"))
        user = User.objects.get(username="asha")
        self.assertTrue(user.check_password("secure-password-123"))
        self.assertEqual(user.student_profile.student_id, "STU-2002")
        self.assertTrue(user.student_profile.reading_lists.filter(is_default=True).exists())
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_catalogue_search_and_book_detail_use_database_records(self):
        response = self.client.get(reverse("core:discover"), {"q": "Database System"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Database System Concepts")
        self.assertNotContains(response, "Artificial Intelligence")

        detail = self.client.get(reverse("core:book_detail_slug", args=["database-system-concepts"]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "DBMS foundations")
        self.assertContains(detail, "9780078022159")

    def test_saved_book_post_toggles_reading_list_item(self):
        self.client.force_login(self.student_user)
        url = reverse("core:save_book", args=["database-system-concepts"])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertTrue(SavedResource.objects.filter(reading_list=self.reading_list, book=self.book).exists())
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(SavedResource.objects.filter(reading_list=self.reading_list, book=self.book).exists())
        self.assertEqual(ActivityLog.objects.filter(action=ActivityLog.Action.SAVE).count(), 1)

    def test_borrow_and_return_update_loan_and_copy_together(self):
        self.client.force_login(self.student_user)
        response = self.client.post(reverse("core:borrow_book", args=["database-system-concepts"]))
        self.assertRedirects(response, reverse("core:book_detail_slug", args=["database-system-concepts"]))
        loan = Loan.objects.get(student=self.student, copy=self.copy)
        self.copy.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.ISSUED)
        self.assertEqual(self.copy.status, BookCopy.Status.ON_LOAN)

        response = self.client.post(reverse("core:return_loan", args=[loan.pk]))
        self.assertRedirects(response, reverse("core:student"))
        loan.refresh_from_db()
        self.copy.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.RETURNED)
        self.assertIsNotNone(loan.returned_at)
        self.assertEqual(self.copy.status, BookCopy.Status.AVAILABLE)

    def test_borrow_queues_reservation_when_all_copies_are_unavailable(self):
        self.copy.status = BookCopy.Status.ON_LOAN
        self.copy.save(update_fields=["status", "updated_at"])
        self.client.force_login(self.student_user)
        response = self.client.post(reverse("core:borrow_book", args=["database-system-concepts"]))
        self.assertEqual(response.status_code, 302)
        reservation = Reservation.objects.get(student=self.student, book=self.book)
        self.assertEqual(reservation.status, Reservation.Status.QUEUED)
        self.assertFalse(Loan.objects.filter(student=self.student, copy=self.copy).exists())

    def test_librarian_catalogue_is_staff_only_and_can_add_book_with_copies(self):
        url = reverse("core:librarian_catalogue")
        self.client.force_login(self.student_user)
        denied = self.client.get(url)
        self.assertEqual(denied.status_code, 302)
        self.assertIn(reverse("core:login"), denied["Location"])

        self.client.force_login(self.staff_user)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        response = self.client.post(url, {
            "title": "Transactions in Practice", "isbn": "9780000000001",
            "publisher": "Academic Press", "copies": "2", "description": "Concurrency control",
        })
        self.assertRedirects(response, url)
        added = Book.objects.get(isbn="9780000000001")
        self.assertEqual(added.copies.count(), 2)
        self.assertEqual(added.copies.filter(status=BookCopy.Status.AVAILABLE).count(), 2)


class SeedLibraryIdempotencyTests(TestCase):
    def test_repeated_seed_keeps_catalogue_and_sample_loan_counts_stable(self):
        call_command("seed_library", students=2, password="demo-password-123")
        counts_after_first = (
            Book.objects.count(), BookCopy.objects.count(), Loan.objects.count(),
            StudentProfile.objects.count(),
        )
        call_command("seed_library", students=2, password="demo-password-123")
        counts_after_second = (
            Book.objects.count(), BookCopy.objects.count(), Loan.objects.count(),
            StudentProfile.objects.count(),
        )
        self.assertEqual(counts_after_second, counts_after_first)
        self.assertEqual(Book.objects.count(), 4)
        self.assertEqual(Loan.objects.count(), 2)
