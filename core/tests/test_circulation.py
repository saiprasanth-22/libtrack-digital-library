"""Circulation rules: issue, request, renew, return and inventory accuracy."""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core import services
from core.models import Book, BookCopy, Loan

from .factories import make_book, make_librarian, make_student

FAST_RULES = {"LOAN_DAYS": 14, "MAX_ACTIVE_LOANS": 3, "MAX_RENEWALS": 1,
               "RENEWAL_DAYS": 7, "DUE_SOON_DAYS": 7, "PAGE_SIZE": 12}


@override_settings(LIBRARY_RULES=FAST_RULES)
class IssueTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_student(username="maya.rao")
        self.book = make_book(title="Database System Concepts", copies=3)
        self.client.force_login(self.user)

    def test_successful_issue_creates_loan_and_consumes_exactly_one_copy(self):
        loan = services.borrow_book(self.profile, self.book)
        self.assertEqual(loan.status, Loan.Status.ISSUED)
        self.assertIsNotNone(loan.issued_at)
        self.assertIsNotNone(loan.due_at)
        self.book.refresh_from_db()
        self.assertEqual(self.book.total_copies, 3)
        self.assertEqual(self.book.available_copies, 2)
        loan.copy.refresh_from_db()
        self.assertEqual(loan.copy.status, BookCopy.Status.ON_LOAN)

    def test_due_date_defaults_to_the_configured_loan_period(self):
        loan = services.borrow_book(self.profile, self.book)
        self.assertEqual(
            (loan.due_at - loan.issued_at).days, FAST_RULES["LOAN_DAYS"])

    def test_issue_is_refused_when_no_copies_are_available(self):
        empty = make_book(title="Fully Borrowed", copies=2)
        BookCopy.objects.filter(book=empty).update(status=BookCopy.Status.ON_LOAN)
        with self.assertRaises(ValidationError) as ctx:
            services.borrow_book(self.profile, empty)
        self.assertIn("No copies", str(ctx.exception))
        self.assertEqual(Loan.objects.filter(book=empty).count(), 0)
        self.assertEqual(empty.available_copies, 0)

    def test_inactive_book_cannot_be_issued(self):
        self.book.is_active = False
        self.book.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            services.borrow_book(self.profile, self.book)

    def test_borrowing_view_issues_and_redirects(self):
        response = self.client.post(
            reverse("core:borrow_book", args=[self.book.slug]))
        self.assertRedirects(response,
                             reverse("core:book_detail", args=[self.book.slug]))
        self.assertTrue(Loan.objects.filter(student=self.profile, status=Loan.Status.ISSUED).exists())

    def test_borrowing_view_shows_message_when_unavailable(self):
        BookCopy.objects.filter(book=self.book).update(status=BookCopy.Status.ON_LOAN)
        response = self.client.post(
            reverse("core:borrow_book", args=[self.book.slug]), follow=True)
        self.assertContains(response, "No copies")
        self.assertEqual(Loan.objects.count(), 0)

    def test_maximum_active_loans_is_enforced(self):
        for index in range(FAST_RULES["MAX_ACTIVE_LOANS"]):
            services.borrow_book(self.profile, make_book(title=f"Title {index}", copies=1))
        self.assertEqual(services.active_loan_count(self.profile), 3)

        with self.assertRaises(ValidationError) as ctx:
            services.borrow_book(self.profile, make_book(title="One Too Many", copies=1))
        self.assertIn("already have 3 books", str(ctx.exception))
        self.assertEqual(services.active_loan_count(self.profile), 3)

    def test_duplicate_active_loan_of_the_same_book_is_blocked(self):
        services.borrow_book(self.profile, self.book)
        with self.assertRaises(ValidationError) as ctx:
            services.borrow_book(self.profile, self.book)
        self.assertIn("already have", str(ctx.exception))
        self.assertEqual(Loan.objects.filter(student=self.profile, book=self.book).count(), 1)

    def test_duplicate_loan_across_different_copies_of_same_title_is_blocked(self):
        services.borrow_book(self.profile, self.book)
        with self.assertRaises(ValidationError):
            services.borrow_book(self.profile, self.book)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 2)

    def test_due_date_cannot_precede_issue_date(self):
        past = timezone.now() - timedelta(days=1)
        with self.assertRaises(ValidationError) as ctx:
            services.borrow_book(self.profile, self.book, due_at=past)
        self.assertIn("after the issue date", str(ctx.exception))


@override_settings(LIBRARY_RULES=FAST_RULES)
class DeactivatedStudentTests(TestCase):
    def test_deactivated_student_cannot_borrow(self):
        _, profile = make_student(username="suspended.one")
        book = make_book()
        profile.is_active = False
        profile.save(update_fields=["is_active"])

        with self.assertRaises(ValidationError) as ctx:
            services.borrow_book(profile, book)
        self.assertIn("deactivated", str(ctx.exception))
        self.assertEqual(Loan.objects.count(), 0)
        self.assertEqual(book.available_copies, 1)

    def test_deactivated_student_cannot_request(self):
        _, profile = make_student(username="suspended.two")
        book = make_book()
        profile.is_active = False
        profile.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            services.request_book(profile, book)
        self.assertEqual(Loan.objects.count(), 0)

    def test_suspended_login_is_blocked_at_the_desk(self):
        librarian = make_librarian()
        _, profile = make_student(username="suspended.three")
        book = make_book()
        profile.is_active = False
        profile.save(update_fields=["is_active"])
        with self.assertRaises(ValidationError):
            services.borrow_book(profile, book, issued_by=librarian)
        self.assertEqual(Loan.objects.count(), 0)

    def test_librarian_can_reactivate_and_borrow_again(self):
        _, profile = make_student(username="returning.one")
        book = make_book()
        profile.is_active = False
        profile.save(update_fields=["is_active"])
        profile.is_active = True
        profile.save(update_fields=["is_active"])
        loan = services.borrow_book(profile, book)
        self.assertEqual(loan.status, Loan.Status.ISSUED)


@override_settings(LIBRARY_RULES=FAST_RULES)
class ReturnTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_student(username="maya.rao")
        self.book = make_book(title="Database System Concepts", copies=2)
        self.loan = services.borrow_book(self.profile, self.book)
        self.client.force_login(self.user)

    def test_successful_return_increases_available_copies_exactly_once(self):
        self.assertEqual(self.book.available_copies, 1)
        services.return_book(self.loan)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 2)
        self.assertEqual(self.book.total_copies, 2)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.RETURNED)
        self.assertIsNotNone(self.loan.returned_at)

    def test_duplicate_return_is_rejected_and_does_not_double_count(self):
        services.return_book(self.loan)
        with self.assertRaises(ValidationError) as ctx:
            services.return_book(self.loan)
        self.assertIn("already been closed", str(ctx.exception))
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 2)

    def test_return_view_works_for_the_owning_student(self):
        response = self.client.post(reverse("core:return_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 302)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.RETURNED)

    def test_return_view_reports_a_second_attempt(self):
        self.client.post(reverse("core:return_loan", args=[self.loan.pk]))
        response = self.client.post(
            reverse("core:return_loan", args=[self.loan.pk]), follow=True)
        self.assertContains(response, "already been closed")
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 2)

    def test_student_cannot_return_someone_elses_loan(self):
        other_user, _ = make_student(username="other.student")
        self.client.force_login(other_user)
        response = self.client.post(reverse("core:return_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 404)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.ISSUED)

    def test_librarian_can_return_any_loan(self):
        librarian = make_librarian()
        self.client.force_login(librarian)
        self.client.post(reverse("core:return_loan", args=[self.loan.pk]))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.RETURNED)
        self.assertEqual(self.loan.received_by, librarian)

    def test_return_cannot_precede_issue(self):
        self.loan.issued_at = timezone.now() - timedelta(days=1)
        self.loan.due_at = timezone.now() + timedelta(days=1)
        self.loan.save(update_fields=["issued_at", "due_at"])
        with self.assertRaises(ValidationError) as ctx:
            services.return_book(self.loan,
                                 returned_at=timezone.now() - timedelta(days=2))
        self.assertIn("earlier than the issue date", str(ctx.exception))

    def test_overdue_return_records_a_fine(self):
        self.loan.issued_at = timezone.now() - timedelta(days=17)
        self.loan.due_at = timezone.now() - timedelta(days=3)
        self.loan.save(update_fields=["issued_at", "due_at"])
        services.return_book(self.loan)
        self.loan.refresh_from_db()
        self.assertGreater(self.loan.fine_amount, 0)


@override_settings(LIBRARY_RULES=FAST_RULES)
class RenewalTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_student(username="maya.rao")
        self.book = make_book(copies=1)
        self.loan = services.borrow_book(self.profile, self.book)
        self.client.force_login(self.user)

    def test_renewal_extends_the_due_date(self):
        original_due = self.loan.due_at
        services.renew_loan(self.loan)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.renewal_count, 1)
        self.assertEqual(self.loan.due_at - original_due,
                         timedelta(days=FAST_RULES["RENEWAL_DAYS"]))

    def test_renewal_is_capped_at_the_configured_maximum(self):
        services.renew_loan(self.loan)
        with self.assertRaises(ValidationError) as ctx:
            services.renew_loan(self.loan)
        self.assertIn("cannot be extended again", str(ctx.exception))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.renewal_count, FAST_RULES["MAX_RENEWALS"])
        self.assertFalse(self.loan.can_renew)

    def test_overdue_loan_cannot_be_renewed(self):
        self.loan.issued_at = timezone.now() - timedelta(days=15)
        self.loan.due_at = timezone.now() - timedelta(days=1)
        self.loan.save(update_fields=["issued_at", "due_at"])
        with self.assertRaises(ValidationError) as ctx:
            services.renew_loan(self.loan)
        self.assertIn("must be returned", str(ctx.exception))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.status, Loan.Status.OVERDUE)

    def test_returned_loan_cannot_be_renewed(self):
        services.return_book(self.loan)
        with self.assertRaises(ValidationError):
            services.renew_loan(self.loan)

    def test_renew_view_requires_login_and_updates_record(self):
        self.client.logout()
        response = self.client.post(reverse("core:renew_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        self.client.post(reverse("core:renew_loan", args=[self.loan.pk]))
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.renewal_count, 1)

    def test_student_cannot_renew_another_students_loan(self):
        other, _ = make_student(username="other.student")
        self.client.force_login(other)
        response = self.client.post(reverse("core:renew_loan", args=[self.loan.pk]))
        self.assertEqual(response.status_code, 404)
        self.loan.refresh_from_db()
        self.assertEqual(self.loan.renewal_count, 0)


@override_settings(LIBRARY_RULES=FAST_RULES)
class OverdueTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_student(username="maya.rao")
        self.book = make_book(copies=2)

    def test_overdue_is_derived_from_due_date(self):
        loan = services.borrow_book(self.profile, self.book)
        self.assertFalse(loan.is_overdue)
        # ``days_until_due`` is a calendar-date difference, so a loan taken at
        # 09:00 has 14 whole days left while one taken at 23:30 has 13 whole
        # days plus the remainder of today. Accept the two valid values so the
        # assertion tests the derivation, not the clock.
        self.assertIn(loan.days_until_due,
                      (FAST_RULES["LOAN_DAYS"], FAST_RULES["LOAN_DAYS"] - 1))

        # Move the whole window back so issued_at still precedes due_at.
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - timedelta(days=15),
            due_at=timezone.now() - timedelta(days=1))
        loan.refresh_from_db()
        self.assertTrue(loan.is_overdue)
        # Same calendar-boundary caveat on the overdue side.
        self.assertIn(loan.days_until_due, (-1, -2))

    def test_sync_updates_stale_issued_rows_to_overdue(self):
        loan = services.borrow_book(self.profile, self.book)
        Loan.objects.filter(pk=loan.pk).update(
            status=Loan.Status.ISSUED,
            issued_at=timezone.now() - timedelta(days=16),
            due_at=timezone.now() - timedelta(days=2))
        self.assertEqual(services.sync_overdue_statuses(), 1)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.OVERDUE)

    def test_returned_loan_is_never_overdue(self):
        loan = services.borrow_book(self.profile, self.book)
        services.return_book(loan)
        loan.refresh_from_db()
        self.assertFalse(loan.is_overdue)

    def test_dashboard_counts_overdue_separately(self):
        overdue_book = make_book(title="Overdue Title", copies=1)
        loan = services.borrow_book(self.profile, overdue_book)
        services.borrow_book(self.profile, self.book)
        services.borrow_book(self.profile, make_book(title="Third", copies=1))
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - timedelta(days=18),
            due_at=timezone.now() - timedelta(days=4))

        data = services.student_dashboard_data(self.profile)
        self.assertEqual(data["active_loans"], 3)
        self.assertEqual(data["overdue_loans"], 1)


@override_settings(LIBRARY_RULES=FAST_RULES)
class RequestApprovalTests(TestCase):
    def setUp(self):
        self.librarian = make_librarian()
        self.user, self.profile = make_student(username="maya.rao")
        self.book = make_book(copies=1)

    def test_request_creates_a_pending_record_without_touching_stock(self):
        loan = services.request_book(self.profile, self.book)
        self.assertEqual(loan.status, Loan.Status.REQUESTED)
        self.assertIsNone(loan.copy)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_duplicate_pending_request_is_blocked(self):
        services.request_book(self.profile, self.book)
        with self.assertRaises(ValidationError):
            services.request_book(self.profile, self.book)
        self.assertEqual(Loan.objects.filter(status=Loan.Status.REQUESTED).count(), 1)

    def test_approving_a_request_consumes_a_copy(self):
        loan = services.request_book(self.profile, self.book)
        services.approve_request(loan, issued_by=self.librarian)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.ISSUED)
        self.assertIsNotNone(loan.copy)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 0)

    def test_approving_without_a_free_copy_keeps_the_request_pending(self):
        loan = services.request_book(self.profile, self.book)
        BookCopy.objects.filter(book=self.book).update(status=BookCopy.Status.ON_LOAN)
        with self.assertRaises(ValidationError) as ctx:
            services.approve_request(loan, issued_by=self.librarian)
        self.assertIn("free yet", str(ctx.exception))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.REQUESTED)

    def test_approval_respects_the_student_loan_limit(self):
        # Queue the request first, then fill the student's allowance.
        loan = services.request_book(self.profile, self.book)
        for index in range(FAST_RULES["MAX_ACTIVE_LOANS"]):
            services.borrow_book(self.profile, make_book(title=f"T{index}", copies=1))
        with self.assertRaises(ValidationError) as ctx:
            services.approve_request(loan, issued_by=self.librarian)
        self.assertIn("already holds 3 books", str(ctx.exception))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.REQUESTED)
        self.assertEqual(self.book.available_copies, 1)

    def test_rejecting_closes_the_request(self):
        loan = services.request_book(self.profile, self.book)
        services.reject_request(loan, reason="Not enough copies", actor=self.librarian)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.REJECTED)
        self.book.refresh_from_db()
        self.assertEqual(self.book.available_copies, 1)

    def test_direct_issue_closes_a_matching_pending_request(self):
        services.request_book(self.profile, self.book)
        services.borrow_book(self.profile, self.book)
        self.assertEqual(Loan.objects.filter(status=Loan.Status.REQUESTED).count(), 0)
        self.assertEqual(Loan.objects.filter(status=Loan.Status.ISSUED).count(), 1)

    def test_librarian_can_approve_from_the_circulation_desk(self):
        loan = services.request_book(self.profile, self.book)
        self.client.force_login(self.librarian)
        self.client.post(reverse("core:librarian_request_approve", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.ISSUED)


@override_settings(LIBRARY_RULES=FAST_RULES)
class InventoryTests(TestCase):
    def test_available_copies_can_never_be_negative(self):
        _, profile = make_student()
        book = make_book(copies=2)
        loan = services.borrow_book(profile, book)
        services.return_book(loan)
        BookCopy.objects.filter(book=book).update(status=BookCopy.Status.ON_LOAN)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 0)
        self.assertGreaterEqual(book.available_copies, 0)

    def test_returning_a_lost_copy_does_not_inflate_the_count(self):
        _, profile = make_student()
        book = make_book(copies=1)
        loan = services.borrow_book(profile, book)
        BookCopy.objects.filter(pk=loan.copy_id).update(status=BookCopy.Status.LOST)
        services.return_book(loan)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 0)
        self.assertEqual(book.total_copies, 1)

    def test_counts_stay_correct_across_a_full_cycle(self):
        _, profile = make_student()
        book = make_book(copies=3)
        for cycle in range(3):
            loan = services.borrow_book(profile, book)
            book.refresh_from_db()
            self.assertEqual((book.available_copies, book.total_copies), (2, 3),
                             f"cycle {cycle}: one copy should be out")
            services.return_book(loan)
            book.refresh_from_db()
            self.assertEqual((book.available_copies, book.total_copies), (3, 3),
                             f"cycle {cycle}: the copy should be back on the shelf")
