"""Book detail tab panels, live availability, reader reviews and redirect safety."""

from django.test import TestCase
from django.urls import reverse

from core import services
from core.models import BookCopy, Loan, Review

from .factories import make_book, make_librarian, make_material, make_student


class TabPanelTests(TestCase):
    """The tab strip must switch real panels, not sit there as decoration."""

    def setUp(self):
        self.book = make_book(title="Database System Concepts", copies=2,
                              authors=("A. Silberschatz",))
        self.url = reverse("core:book_detail", args=[self.book.slug])

    def test_every_tab_button_is_wired_to_a_panel(self):
        response = self.client.get(self.url)
        html = response.content.decode()
        panels = {"overview", "availability", "resources", "reviews"}
        for name in panels:
            self.assertIn(f'data-tab="{name}"', html)
            self.assertIn(f'data-panel="{name}"', html)
        # Each button points at a panel that actually exists in the same page.
        for name in panels:
            self.assertIn(f'aria-controls="panel-{name}"', html)

    def test_all_panels_are_in_the_html_so_the_page_works_without_javascript(self):
        html = self.client.get(self.url).content.decode()
        for name in ("overview", "availability", "resources", "reviews"):
            self.assertIn(f'id="panel-{name}"', html)
        # Progressive enhancement: the hiding class is only added by tabs.js.
        self.assertNotIn("detail-panels is-ready", html)

    def test_only_the_first_panel_is_marked_active(self):
        html = self.client.get(self.url).content.decode()
        self.assertIn('class="detail-panel is-active"', html)
        self.assertEqual(html.count("is-active"), 1)


class AvailabilityPanelTests(TestCase):
    """The Availability tab reports the real shelf state, not a hardcoded number."""

    def setUp(self):
        self.book = make_book(copies=3)
        self.copies = list(self.book.copies.order_by("accession_number"))
        self.url = reverse("core:book_detail", args=[self.book.slug])

    def test_panel_lists_every_accession_number(self):
        response = self.client.get(self.url)
        for copy in self.copies:
            self.assertContains(response, copy.accession_number)
        self.assertEqual(len(response.context["copies"]), 3)

    def test_availability_reflects_a_copy_leaving_the_shelf(self):
        _, student = make_student()
        services.borrow_book(student, self.book)
        response = self.client.get(self.url)
        self.assertEqual(response.context["book"].available_copies, 2)
        self.assertContains(response, "On loan")
        # The copy that went out is no longer reported as available.
        self.assertEqual(
            sum(1 for c in response.context["copies"] if c.status == BookCopy.Status.AVAILABLE),
            2)

    def test_a_book_with_no_copies_still_renders_the_panel(self):
        empty = make_book(title="Manuscript Without Copies", copies=0)
        response = self.client.get(reverse("core:book_detail", args=[empty.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No physical copies are catalogued")
        self.assertEqual(response.context["book"].total_copies, 0)

    def test_status_breakdown_counts_really_add_up(self):
        copy = BookCopy.objects.filter(book=self.book).order_by("pk").first()
        copy.status = BookCopy.Status.REPAIR
        copy.save(update_fields=["status"])
        response = self.client.get(self.url)
        breakdown = {row["status"]: row["count"]
                     for row in response.context["status_breakdown"]}
        self.assertEqual(sum(breakdown.values()), 3)
        self.assertEqual(breakdown[BookCopy.Status.AVAILABLE], 2)
        self.assertEqual(breakdown[BookCopy.Status.REPAIR], 1)


class ReaderReviewTests(TestCase):
    def setUp(self):
        self.book = make_book(copies=1)
        self.student, self.profile = make_student()
        self.client.force_login(self.student)
        self.url = reverse("core:book_detail", args=[self.book.slug])
        self.post = reverse("core:book_review", args=[self.book.slug])

    def _return_the_book(self):
        loan = services.borrow_book(self.profile, self.book)
        services.return_book(loan)

    def test_a_borrower_can_publish_a_review(self):
        self._return_the_book()
        response = self.client.post(self.post, {
            "rating": 5, "title": "Essential", "body": "Clarified normalisation for me."},
            follow=True)
        self.assertEqual(response.status_code, 200)
        review = Review.objects.get(student=self.profile, book=self.book)
        self.assertEqual(review.rating, 5)
        self.assertEqual(review.title, "Essential")
        self.assertTrue(review.is_published)
        self.assertContains(response, "Clarified normalisation for me.")

    def test_a_subsequent_submission_edits_instead_of_duplicating(self):
        self._return_the_book()
        self.client.post(self.post, {"rating": 3, "title": "First", "body": ""})
        self.client.post(self.post, {"rating": 4, "title": "Second", "body": ""})
        self.assertEqual(Review.objects.filter(
            student=self.profile, book=self.book).count(), 1)
        self.assertEqual(Review.objects.get().rating, 4)

    def test_a_student_who_never_borrowed_cannot_review(self):
        response = self.client.post(self.post, {"rating": 5, "body": ""}, follow=True)
        self.assertFalse(Review.objects.exists())
        self.assertContains(response, "only review a book you have borrowed")

    def test_a_student_still_holding_the_book_cannot_review_yet(self):
        services.borrow_book(self.profile, self.book)
        self.client.post(self.post, {"rating": 5, "body": ""})
        self.assertFalse(Review.objects.exists())

    def test_rating_outside_one_to_five_is_rejected(self):
        self._return_the_book()
        for bad in ("0", "6", "", "abc"):
            self.client.post(self.post, {"rating": bad, "body": ""})
        self.assertFalse(Review.objects.exists())

    def test_review_counts_reach_the_tab_badge(self):
        self._return_the_book()
        self.client.post(self.post, {"rating": 4, "body": "Solid"})
        response = self.client.get(self.url)
        self.assertEqual(response.context["rating_count"], 1)
        self.assertAlmostEqual(response.context["rating_average"], 4.0, places=1)
        self.assertContains(response, "4.0 out of 5")

    def test_a_reviewer_cannot_review_someone_elses_book_or_others_review(self):
        self._return_the_book()
        self.client.post(self.post, {"rating": 5, "body": "Mine"})
        other, other_profile = make_student(username="other.reviewer")
        services.borrow_book(other_profile, self.book)
        services.return_book(Loan.objects.filter(student=other_profile).first())
        self.client.force_login(other)
        self.client.post(self.post, {"rating": 1, "body": "Hijack"})
        self.assertEqual(Review.objects.count(), 2)
        self.assertEqual(Review.objects.get(student=self.profile).rating, 5)

    def test_anonymous_visitors_cannot_post_a_review(self):
        self.client.logout()
        response = self.client.post(self.post, {"rating": 5, "body": ""})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("core:login"), response["Location"])
        self.assertFalse(Review.objects.exists())

    def test_staff_do_not_get_a_review_form(self):
        librarian = make_librarian(username="review.staff")
        self.client.force_login(librarian)
        response = self.client.get(self.url)
        self.assertFalse(response.context["can_review"])
        self.assertNotContains(response, "Publish review")


class ReviewActionLoggedTests(TestCase):
    def test_publishing_a_review_writes_an_audit_row(self):
        book = make_book(copies=1)
        user, profile = make_student()
        services.borrow_book(profile, book)
        services.return_book(Loan.objects.filter(student=profile).first())
        self.client.force_login(user)
        self.client.post(reverse("core:book_review", args=[book.slug]),
                         {"rating": 5, "body": ""})
        self.assertTrue(profile.activities.filter(action="review").exists())


class OpenRedirectTests(TestCase):
    """A forged `next` must never bounce a user off the site."""

    def setUp(self):
        self.book = make_book(copies=1)
        self.user, self.profile = make_student()

    def _host(self, response):
        return response["Location"]

    def test_login_ignores_an_absolute_next(self):
        response = self.client.post(reverse("core:login"), {
            "username": self.user.username, "password": "test-pass-4321",
            "next": "https://evil.example/steal"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self._host(response), reverse("core:student"))

    def test_login_ignores_a_protocol_relative_next(self):
        response = self.client.post(reverse("core:login"), {
            "username": self.user.username, "password": "test-pass-4321",
            "next": "//evil.example/steal"})
        self.assertEqual(self._host(response), reverse("core:student"))

    def test_login_still_honours_a_safe_local_next(self):
        response = self.client.post(reverse("core:login"), {
            "username": self.user.username, "password": "test-pass-4321",
            "next": "/discover/"})
        self.assertEqual(self._host(response), "/discover/")

    def test_save_book_ignores_an_absolute_next(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:save_book", args=[self.book.slug]),
            {"next": "https://evil.example/steal"})
        self.assertEqual(self._host(response), f"/books/{self.book.slug}/")

    def test_return_loan_ignores_an_absolute_next(self):
        loan = services.borrow_book(self.profile, self.book)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:return_loan", args=[loan.pk]),
            {"next": "https://evil.example/steal"})
        self.assertEqual(self._host(response), reverse("core:dashboard"))

    def test_renew_loan_ignores_an_absolute_next(self):
        loan = services.borrow_book(self.profile, self.book)
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("core:renew_loan", args=[loan.pk]),
            {"next": "https://evil.example/steal"})
        self.assertEqual(self._host(response), reverse("core:student_loans"))


class DigitalResourcesPanelTests(TestCase):
    def test_resources_panel_links_to_each_material(self):
        book = make_book()
        material = make_material(title="Indexing Strategies",
                                 external_url="https://example.edu/papers/indexing")
        book.digital_materials.add(material)
        response = self.client.get(reverse("core:book_detail", args=[book.slug]))
        self.assertContains(response, "Indexing Strategies")
        self.assertContains(response, "https://example.edu/papers/indexing")

    def test_resources_panel_explains_an_empty_state(self):
        book = make_book()
        response = self.client.get(reverse("core:book_detail", args=[book.slug]))
        self.assertContains(response, "No digital material is attached")
