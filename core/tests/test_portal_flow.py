"""Public landing and role-specific authentication gateway."""

from django.test import TestCase
from django.urls import reverse

from .factories import make_book, make_librarian, make_student


class PortalFlowTests(TestCase):
    def setUp(self):
        self.student, _ = make_student(username="reader", password="test-pass-4321")
        self.librarian = make_librarian(username="desk", password="test-pass-4321")
        self.book = make_book(title="Gateway Book")

    def test_hero_is_public_and_portal_has_exact_role_choices(self):
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
        response = self.client.get(reverse("core:portal_select"))
        self.assertContains(response, "Student Portal")
        self.assertContains(response, "Librarian Portal")
        self.assertContains(response, reverse("core:student_login"))
        self.assertContains(response, reverse("core:librarian_login"))

    def test_application_deep_links_pass_through_portal_selector(self):
        routes = [
            reverse("core:discover"), reverse("core:materials"),
            reverse("core:book_detail", args=[self.book.slug]),
            reverse("core:study_buddy"), reverse("core:student"),
            reverse("core:librarian"),
        ]
        for path in routes:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response.url.startswith(reverse("core:portal_select")))
                self.assertIn("next=", response.url)

    def test_student_and_librarian_sign_in_to_their_own_dashboards(self):
        response = self.client.post(reverse("core:student_login"), {
            "username": "reader", "password": "test-pass-4321"})
        self.assertRedirects(response, reverse("core:student"))
        self.client.logout()
        response = self.client.post(reverse("core:librarian_login"), {
            "username": "desk", "password": "test-pass-4321"})
        self.assertRedirects(response, reverse("core:librarian"))

    def test_each_portal_rejects_the_other_roles_credentials(self):
        response = self.client.post(reverse("core:student_login"), {
            "username": "desk", "password": "test-pass-4321"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "other LibTrack portal")
        self.assertNotIn("_auth_user_id", self.client.session)
        response = self.client.post(reverse("core:librarian_login"), {
            "username": "reader", "password": "test-pass-4321"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_student_registration_is_not_offered_at_librarian_login(self):
        response = self.client.get(reverse("core:librarian_login"))
        self.assertNotContains(response, "Create a student account")
        self.assertContains(self.client.get(reverse("core:student_login")),
                            "Create a student account")

    def test_each_login_suggests_the_matching_demo_username(self):
        student = self.client.get(reverse("core:student_login"))
        librarian = self.client.get(reverse("core:librarian_login"))
        self.assertContains(student, 'placeholder="maya.rao"')
        self.assertNotContains(student, 'placeholder="library.admin"')
        self.assertContains(librarian, 'placeholder="library.admin"')
        self.assertNotContains(librarian, 'placeholder="maya.rao"')

    def test_safe_role_appropriate_next_is_preserved(self):
        target = reverse("core:book_detail", args=[self.book.slug])
        response = self.client.post(reverse("core:student_login"), {
            "username": "reader", "password": "test-pass-4321", "next": target})
        self.assertRedirects(response, target)

    def test_external_and_wrong_role_next_are_rejected(self):
        for target in ("https://evil.example/steal", "//evil.example/steal",
                       reverse("core:librarian")):
            self.client.logout()
            response = self.client.post(reverse("core:student_login"), {
                "username": "reader", "password": "test-pass-4321", "next": target})
            self.assertRedirects(response, reverse("core:student"))

    def test_legacy_login_only_redirects_to_role_chooser(self):
        response = self.client.get(reverse("core:login"), {"next": reverse("core:discover")})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("core:portal_select")))
        response = self.client.post(reverse("core:login"), {
            "username": "reader", "password": "test-pass-4321"})
        self.assertRedirects(response, reverse("core:portal_select"),
                             fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_ambiguous_student_next_paths_cannot_cross_into_staff_routes(self):
        hostile = (
            "/books/../librarian/",
            "/books/%2e%2e/librarian/",
            "/books/%252e%252e/librarian/",
            "/books\\..\\librarian/",
            "//evil.example/librarian/",
            "/%2flibrarian/",
        )
        for target in hostile:
            with self.subTest(target=target):
                self.client.logout()
                response = self.client.post(reverse("core:student_login"), {
                    "username": "reader", "password": "test-pass-4321", "next": target})
                self.assertRedirects(response, reverse("core:student"))

    def test_librarian_cannot_use_ambiguous_next_to_enter_student_routes(self):
        for target in ("/librarian/../student/", "/librarian/%2e%2e/discover/",
                       "/librarian\\..\\student/"):
            with self.subTest(target=target):
                self.client.logout()
                response = self.client.post(reverse("core:librarian_login"), {
                    "username": "desk", "password": "test-pass-4321", "next": target})
                self.assertRedirects(response, reverse("core:librarian"))

    def test_authenticated_users_bypass_selector(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse("core:portal_select")),
                             reverse("core:dashboard"), fetch_redirect_response=False)

    def test_logout_is_post_only_and_returns_to_hero(self):
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(reverse("core:logout")).status_code, 405)
        self.assertRedirects(self.client.post(reverse("core:logout")), reverse("core:home"))
