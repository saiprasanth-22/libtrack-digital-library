"""Librarian workflows: catalogue CRUD, students, circulation and reports."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core import services
from core.models import ActivityLog, Book, BookCopy, DigitalMaterial, Loan, StudentProfile

from .factories import (make_book, make_librarian, make_material, make_student,
                        next_id)

RULES = {"LOAN_DAYS": 14, "MAX_ACTIVE_LOANS": 3, "MAX_RENEWALS": 1,
         "RENEWAL_DAYS": 7, "DUE_SOON_DAYS": 7, "PAGE_SIZE": 12}


class LibrarianTestCase(TestCase):
    def setUp(self):
        self.librarian = make_librarian(username="library.admin")
        self.client.force_login(self.librarian)


class BookManagementTests(LibrarianTestCase):
    def test_librarian_can_add_a_book_with_copies(self):
        response = self.client.post(reverse("core:librarian_books"), {
            "title": "Transactions in Practice",
            "isbn": "9780000000001",
            "publisher": "Academic Press",
            "publication_year": 2021,
            "description": "Concurrency control in practice.",
            "total_copies": "3",
        })
        self.assertRedirects(response, reverse("core:librarian_books"))
        book = Book.objects.get(isbn="9780000000001")
        self.assertEqual(book.total_copies, 3)
        self.assertEqual(book.available_copies, 3)
        self.assertEqual(book.slug, "transactions-in-practice")
        self.assertTrue(ActivityLog.objects.filter(action=ActivityLog.Action.ADMIN).exists())

    def test_librarian_added_book_is_visible_in_the_public_catalogue(self):
        """A title added at the desk must actually appear for students.

        `is_active` is a checkbox, so an unchecked box silently creates a book
        that is hidden everywhere. This guards that regression.
        """
        self.client.post(reverse("core:librarian_books"), {
            "title": "Visible In Catalogue",
            "isbn": "9780000000009",
            "total_copies": "2",
            "is_active": "on",
        })
        book = Book.objects.get(isbn="9780000000009")
        self.assertTrue(book.is_active)

        response = self.client.get(reverse("core:discover"), {"q": "Visible In Catalogue"})
        self.assertContains(response, "Visible In Catalogue")

        detail = self.client.get(reverse("core:book_detail", args=[book.slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "2 of 2 copies")

    def test_a_retired_book_disappears_from_the_catalogue(self):
        """Both delete paths must remove the title from the public catalogue.

        Asserted against the rendered result set rather than the raw HTML,
        because the search term itself is echoed back in the search box.
        """
        _, profile = make_student()
        # No history -> removed outright.
        removable = make_book(title="Removable Title", copies=1)
        self.client.post(reverse("core:librarian_book_delete", args=[removable.pk]))
        self.assertFalse(Book.objects.filter(pk=removable.pk).exists())
        self.assertEqual(
            self.client.get(reverse("core:book_detail", args=[removable.slug])).status_code, 404)

        # Has history -> retired, so the record and its loans survive.
        kept = make_book(title="Retained Title", copies=1)
        services.borrow_book(profile, kept)
        self.client.post(reverse("core:librarian_book_delete", args=[kept.pk]))
        kept.refresh_from_db()
        self.assertFalse(kept.is_active)
        self.assertTrue(Loan.objects.filter(book=kept).exists())
        self.assertEqual(
            self.client.get(reverse("core:book_detail", args=[kept.slug])).status_code, 404)

        for title in ("Removable Title", "Retained Title"):
            with self.subTest(title=title):
                response = self.client.get(reverse("core:discover"), {"q": title})
                listed = [b.title for b in response.context["books"]]
                self.assertNotIn(title, listed)
                self.assertEqual(response.context["total_results"], 0)

    def test_adding_a_book_without_a_title_is_rejected(self):
        response = self.client.post(reverse("core:librarian_books"), {
            "title": "", "total_copies": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required")
        self.assertEqual(Book.objects.count(), 0)

    def test_negative_copy_count_is_rejected(self):
        response = self.client.post(reverse("core:librarian_books"), {
            "title": "Bad Inventory", "total_copies": "-2"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Book.objects.filter(title="Bad Inventory").exists())

    def test_librarian_can_edit_a_book(self):
        book = make_book(title="Old Title", copies=2)
        response = self.client.post(reverse("core:librarian_book_edit", args=[book.pk]), {
            "title": "New Title", "isbn": book.isbn, "publisher": "New Press",
            "publication_year": 2020, "total_copies": "4",
        })
        self.assertRedirects(response, reverse("core:librarian_books"))
        book.refresh_from_db()
        self.assertEqual(book.title, "New Title")
        self.assertEqual(book.publisher, "New Press")
        self.assertEqual(book.total_copies, 4)

    def test_editing_can_withdraw_idle_copies(self):
        book = make_book(title="Shrinkable", copies=5)
        self.client.post(reverse("core:librarian_book_edit", args=[book.pk]), {
            "title": book.title, "isbn": book.isbn, "total_copies": "2"})
        book.refresh_from_db()
        self.assertEqual(book.total_copies, 2)

    def test_withdrawing_a_copy_that_is_on_loan_never_goes_negative(self):
        _, profile = make_student()
        book = make_book(title="On Loan", copies=2)
        services.borrow_book(profile, book)  # 1 of 2 now on loan

        self.client.post(reverse("core:librarian_book_edit", args=[book.pk]), {
            "title": book.title, "isbn": book.isbn, "total_copies": "0"})
        book.refresh_from_db()
        # Only the idle copy can be removed, so one remains out on loan.
        self.assertEqual(book.total_copies, 1)
        self.assertEqual(book.available_copies, 0)
        self.assertGreaterEqual(book.available_copies, 0)

    def test_deleting_a_book_with_history_retires_it_instead(self):
        _, profile = make_student()
        book = make_book(title="Has History", copies=1)
        services.borrow_book(profile, book)

        self.client.post(reverse("core:librarian_book_delete", args=[book.pk]))
        book.refresh_from_db()
        self.assertFalse(book.is_active)
        self.assertTrue(Loan.objects.filter(book=book).exists())  # history preserved
        self.assertTrue(Book.objects.filter(pk=book.pk).exists())

    def test_deleting_a_book_without_history_removes_it(self):
        book = make_book(title="Disposable", copies=1)
        self.client.post(reverse("core:librarian_book_delete", args=[book.pk]))
        self.assertFalse(Book.objects.filter(pk=book.pk).exists())

    def test_librarian_can_add_and_edit_copies(self):
        book = make_book(title="Copy Management", copies=1)
        self.client.post(reverse("core:librarian_copies", args=[book.pk]), {
            "action": "add", "shelf_location": "A-01"})
        book.refresh_from_db()
        self.assertEqual(book.total_copies, 2)

        copy = book.copies.order_by("accession_number").first()
        self.client.post(reverse("core:librarian_copies", args=[book.pk]), {
            "copy_id": copy.pk, "accession_number": copy.accession_number,
            "status": BookCopy.Status.REPAIR, "shelf_location": "A-01"})
        copy.refresh_from_db()
        self.assertEqual(copy.status, BookCopy.Status.REPAIR)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)

    def test_catalogue_search_filters_the_admin_list(self):
        make_book(title="Database System Concepts")
        make_book(title="Pragmatic Programmer")
        response = self.client.get(reverse("core:librarian_books"), {"q": "Pragmatic"})
        titles = [b.title for b in response.context["books"]]
        self.assertEqual(titles, ["Pragmatic Programmer"])


class StudentManagementTests(LibrarianTestCase):
    def test_librarian_can_search_students(self):
        make_student(username="maya.rao", student_id="STU-1001", first_name="Maya",
                     last_name="Rao")
        make_student(username="arjun.nair", student_id="STU-1002", first_name="Arjun",
                     last_name="Nair")
        response = self.client.get(reverse("core:librarian_students"), {"q": "Maya"})
        self.assertEqual(len(response.context["students"]), 1)
        self.assertContains(response, "STU-1001")

    def test_student_list_never_shows_a_password(self):
        user, _ = make_student(username="maya.rao")
        response = self.client.get(reverse("core:librarian_students"))
        self.assertNotContains(response, user.password)
        self.assertNotContains(response, "test-pass-4321")

    def test_librarian_can_deactivate_and_reactivate(self):
        user, profile = make_student(username="maya.rao")
        self.client.post(reverse("core:librarian_student_toggle", args=[profile.pk]))
        profile.refresh_from_db()
        user.refresh_from_db()
        self.assertFalse(profile.is_active)
        self.assertFalse(user.is_active)

        self.client.post(reverse("core:librarian_student_toggle", args=[profile.pk]))
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)

    def test_deactivating_preserves_borrowing_history(self):
        _, profile = make_student()
        book = make_book(copies=1)
        services.borrow_book(profile, book)
        self.client.post(reverse("core:librarian_student_toggle", args=[profile.pk]))
        profile.refresh_from_db()
        self.assertFalse(profile.is_active)
        self.assertEqual(Loan.objects.filter(student=profile).count(), 1)

    def test_librarian_cannot_deactivate_their_own_account(self):
        profile = StudentProfile.objects.create(
            user=self.librarian, student_id="STU-0001", department="Library")
        self.client.post(reverse("core:librarian_student_toggle", args=[profile.pk]))
        profile.refresh_from_db()
        self.assertTrue(profile.is_active)

    def test_student_detail_shows_borrowing_breakdown(self):
        _, profile = make_student()
        book = make_book(copies=2)
        services.borrow_book(profile, book)
        services.borrow_book(profile, make_book(copies=1))
        services.return_book(Loan.objects.filter(student=profile).last())
        response = self.client.get(reverse("core:librarian_student_detail", args=[profile.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, profile.student_id)
        self.assertEqual(len(response.context["active_loans"]), 1)
        self.assertEqual(len(response.context["returned_loans"]), 1)


class CirculationDeskTests(LibrarianTestCase):
    def test_librarian_issues_a_book_to_a_student(self):
        user, profile = make_student(username="maya.rao")
        book = make_book(title="Database System Concepts", copies=2)
        response = self.client.post(reverse("core:librarian_circulation"), {
            "action": "issue", "student": profile.pk, "book": book.pk, "due_at": ""})
        self.assertRedirects(response, reverse("core:librarian_circulation"))
        loan = Loan.objects.get(student=profile, status=Loan.Status.ISSUED)
        self.assertEqual(loan.issued_by, self.librarian)
        book.refresh_from_db()
        self.assertEqual(book.available_copies, 1)

    def test_issuing_reports_an_error_instead_of_crashing(self):
        _, profile = make_student()
        book = make_book(copies=1)
        services.borrow_book(profile, book)
        BookCopy.objects.filter(book=book).update(status=BookCopy.Status.ON_LOAN)

        other_book = make_book(copies=1)
        BookCopy.objects.filter(book=other_book).update(status=BookCopy.Status.ON_LOAN)
        response = self.client.post(reverse("core:librarian_circulation"), {
            "action": "issue", "student": profile.pk, "book": other_book.pk, "due_at": ""},
            follow=True)
        self.assertContains(response, "No copies")
        self.assertEqual(Loan.objects.filter(status=Loan.Status.ISSUED).count(), 1)

    def test_issuing_with_custom_due_date_is_respected(self):
        _, profile = make_student()
        book = make_book(copies=1)
        due = (timezone.now() + timedelta(days=21)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(reverse("core:librarian_circulation"), {
            "action": "issue", "student": profile.pk, "book": book.pk, "due_at": due})
        loan = Loan.objects.get(status=Loan.Status.ISSUED)
        self.assertAlmostEqual((loan.due_at - loan.issued_at).days, 21, delta=1)

    def test_circulation_page_lists_pending_requests(self):
        _, profile = make_student()
        book = make_book()
        loan = services.request_book(profile, book)
        response = self.client.get(reverse("core:librarian_circulation"))
        self.assertContains(response, book.title)
        self.assertEqual(len(response.context["pending_requests"]), 1)

    def test_librarian_rejects_a_request(self):
        _, profile = make_student()
        loan = services.request_book(profile, make_book())
        self.client.post(reverse("core:librarian_request_reject", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.REJECTED)

    def test_return_from_desk_records_the_receiving_staff_member(self):
        _, profile = make_student()
        loan = services.borrow_book(profile, make_book(copies=1))
        self.client.post(reverse("core:return_loan", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.RETURNED)
        self.assertEqual(loan.received_by, self.librarian)


class MaterialManagementTests(LibrarianTestCase):
    def test_librarian_can_add_a_public_material(self):
        response = self.client.post(reverse("core:librarian_materials"), {
            "title": "Indexing Strategies",
            "material_type": DigitalMaterial.MaterialType.PAPER,
            "external_url": "https://example.edu/papers/indexing",
            "is_public": "on",
        })
        self.assertRedirects(response, reverse("core:librarian_materials"))
        material = DigitalMaterial.objects.get(title="Indexing Strategies")
        self.assertTrue(material.is_public)

    def test_material_without_a_source_is_rejected(self):
        response = self.client.post(reverse("core:librarian_materials"), {
            "title": "No Source", "material_type": DigitalMaterial.MaterialType.NOTES})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DigitalMaterial.objects.filter(title="No Source").exists())

    def test_hidden_material_is_not_shown_to_students(self):
        make_material(title="Internal Only", is_public=False)
        self.client.logout()
        response = self.client.get(reverse("core:materials"))
        self.assertNotContains(response, "Internal Only")

    def test_librarian_can_edit_and_delete(self):
        material = make_material(title="Editable")
        self.client.post(reverse("core:librarian_material_edit", args=[material.pk]), {
            "title": "Edited", "material_type": material.material_type,
            "external_url": "https://example.edu/edited", "is_public": "on"})
        material.refresh_from_db()
        self.assertEqual(material.title, "Edited")

        self.client.post(reverse("core:librarian_material_delete", args=[material.pk]))
        self.assertFalse(DigitalMaterial.objects.filter(pk=material.pk).exists())

    def test_material_can_be_linked_to_a_book(self):
        book = make_book(title="Database System Concepts")
        make_material(title="Linked Notes", book=book)
        self.assertEqual(book.digital_materials.count(), 1)


class ReportTests(LibrarianTestCase):
    def setUp(self):
        super().setUp()
        _, self.profile = make_student(username="maya.rao")
        self.popular = make_book(title="Popular Title", copies=3)
        self.quiet = make_book(title="Quiet Title", copies=1)
        for _ in range(3):
            loan = services.borrow_book(self.profile, self.popular)
            services.return_book(loan)
        services.borrow_book(self.profile, self.quiet)

    def test_reports_page_renders_with_live_figures(self):
        response = self.client.get(reverse("core:librarian_reports"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Most borrowed titles")
        self.assertContains(response, "Popular Title")
        report = response.context["report"]
        self.assertEqual(report["total_books"], 2)
        self.assertEqual(report["current_loans"], 1)
        self.assertEqual(report["returned_in_period"], 3)

    def test_most_borrowed_is_ordered_by_count(self):
        report = services.librarian_report_data()
        titles = [b.title for b in report["top_borrowed"]]
        self.assertEqual(titles[0], "Popular Title")

    def test_date_range_filter_is_applied(self):
        future = timezone.now() + timedelta(days=5)
        report = services.librarian_report_data(start=timezone.now(), end=future)
        self.assertEqual(report["returned_in_period"], 0)

    def test_dashboard_counters_match_the_database(self):
        stats = services.librarian_dashboard_data()
        self.assertEqual(stats["total_books"], 2)
        self.assertEqual(stats["total_copies"], 4)
        self.assertEqual(stats["available_copies"], 3)
        self.assertEqual(stats["current_loans"], 1)
        self.assertEqual(stats["student_count"], 1)
        self.assertEqual(stats["overdue_count"], 0)

    def test_dashboard_page_shows_aggregated_numbers(self):
        response = self.client.get(reverse("core:librarian"))
        self.assertContains(response, "Popular Title")
        self.assertContains(response, "Quiet Title")
        self.assertEqual(response.context["stats"]["total_copies"], 4)

    def test_overdue_appears_in_the_report(self):
        loan = Loan.objects.filter(status=Loan.Status.ISSUED).first()
        Loan.objects.filter(pk=loan.pk).update(
            issued_at=timezone.now() - timedelta(days=17),
            due_at=timezone.now() - timedelta(days=3))
        report = services.librarian_report_data()
        self.assertEqual(report["overdue_loans"], 1)
        self.assertEqual(len(report["overdue_loans_qs"]), 1)


class AuditTrailTests(LibrarianTestCase):
    def test_borrow_and_return_are_audited(self):
        _, profile = make_student()
        book = make_book(copies=1)
        loan = services.borrow_book(profile, book, issued_by=self.librarian)
        services.return_book(loan, received_by=self.librarian)
        actions = set(ActivityLog.objects.values_list("action", flat=True))
        self.assertIn(ActivityLog.Action.BORROW, actions)
        self.assertIn(ActivityLog.Action.RETURN, actions)

    def test_renewal_is_audited_with_the_new_due_date(self):
        _, profile = make_student()
        loan = services.borrow_book(profile, make_book(copies=1))
        services.renew_loan(loan, actor=self.librarian)
        event = ActivityLog.objects.filter(action=ActivityLog.Action.RENEW).latest("occurred_at")
        self.assertIn("due_at", event.metadata)
