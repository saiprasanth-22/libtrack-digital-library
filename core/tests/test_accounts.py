"""Registration, login, password rules and route protection."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from core.models import ReadingList, StudentProfile

from .factories import make_librarian, make_student

User = get_user_model()

VALID_REGISTRATION = {
    "first_name": "Asha",
    "last_name": "Iyer",
    "email": "asha.iyer@example.test",
    "username": "asha.iyer",
    "student_id": "STU-7788",
    "department": "Physics",
    "semester": 4,
    "phone": "9000000000",
    "enrollment_year": 2024,
    "password1": "Library-Reader-2026",
    "password2": "Library-Reader-2026",
}


class RegistrationTests(TestCase):
    def test_registration_creates_user_profile_and_default_reading_list(self):
        response = self.client.post(reverse("core:register"), VALID_REGISTRATION)
        self.assertRedirects(response, reverse("core:student"))

        user = User.objects.get(username="asha.iyer")
        self.assertTrue(user.check_password("Library-Reader-2026"))
        self.assertNotEqual(user.password, "Library-Reader-2026")  # stored hashed

        profile = user.student_profile
        self.assertEqual(profile.student_id, "STU-7788")
        self.assertEqual(profile.semester, 4)
        self.assertTrue(profile.reading_lists.filter(is_default=True).exists())
        self.assertTrue(self.client.session.get("_auth_user_id"))

    def test_duplicate_registration_number_is_rejected(self):
        make_student(student_id="STU-7788")
        response = self.client.post(reverse("core:register"), VALID_REGISTRATION)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already registered")
        self.assertFalse(User.objects.filter(username="asha.iyer").exists())

    def test_duplicate_email_is_rejected(self):
        _, profile = make_student(email="asha.iyer@example.test")
        payload = dict(VALID_REGISTRATION, email=profile.user.email)
        response = self.client.post(reverse("core:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")

    def test_mismatched_password_confirmation_is_rejected(self):
        payload = dict(VALID_REGISTRATION, password2="Something-Else-2026")
        response = self.client.post(reverse("core:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha.iyer").exists())

    def test_weak_password_is_rejected_by_django_validators(self):
        payload = dict(VALID_REGISTRATION, password1="password", password2="password")
        response = self.client.post(reverse("core:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha.iyer").exists())

    def test_semester_outside_range_is_rejected(self):
        payload = dict(VALID_REGISTRATION, semester=15)
        response = self.client.post(reverse("core:register"), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="asha.iyer").exists())


class LoginTests(TestCase):
    def test_student_login_redirects_to_student_dashboard(self):
        make_student(username="maya.rao", password="LibTrackDemo2026!")
        response = self.client.post(
            reverse("core:student_login"), {"username": "maya.rao", "password": "LibTrackDemo2026!"})
        self.assertRedirects(response, reverse("core:student"))

    def test_librarian_login_redirects_to_librarian_dashboard(self):
        make_librarian(username="library.admin", password="LibTrackDemo2026!")
        response = self.client.post(
            reverse("core:librarian_login"), {"username": "library.admin", "password": "LibTrackDemo2026!"})
        self.assertRedirects(response, reverse("core:librarian"))

    def test_wrong_password_shows_friendly_error_and_no_login(self):
        make_student(username="maya.rao", password="LibTrackDemo2026!")
        response = self.client.post(
            reverse("core:student_login"), {"username": "maya.rao", "password": "wrong-password"},
            follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "did not match an account")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_deactivated_login_is_refused(self):
        user, _ = make_student(username="suspended.user", email="suspended@example.test")
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("core:student_login"), {"username": "suspended.user", "password": "test-pass-4321"},
            follow=True)
        self.assertContains(response, "deactivated")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_wrong_password_does_not_reveal_that_an_account_is_deactivated(self):
        user, _ = make_student(username="suspended.user")
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("core:student_login"), {"username": "suspended.user", "password": "guessing"},
            follow=True)
        self.assertContains(response, "did not match an account")
        self.assertNotContains(response, "deactivated")

    def test_logout_requires_post_and_ends_session(self):
        make_student(username="maya.rao")
        self.client.force_login(User.objects.get(username="maya.rao"))
        self.assertEqual(self.client.get(reverse("core:logout")).status_code, 405)
        self.client.post(reverse("core:logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class RouteProtectionTests(TestCase):
    STUDENT_ROUTES = [
        ("core:student", {}),
        ("core:student_loans", {}),
        ("core:student_profile", {}),
    ]
    STAFF_ROUTES = [
        ("core:librarian", {}),
        ("core:librarian_books", {}),
        ("core:librarian_students", {}),
        ("core:librarian_circulation", {}),
        ("core:librarian_materials", {}),
        ("core:librarian_reports", {}),
    ]

    def test_anonymous_users_are_redirected_to_login(self):
        for name, kwargs in self.STUDENT_ROUTES + self.STAFF_ROUTES:
            with self.subTest(route=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("core:portal_select"), response["Location"])

    def test_students_cannot_open_librarian_pages(self):
        user, _ = make_student(username="plain.student")
        self.client.force_login(user)
        for name, kwargs in self.STAFF_ROUTES:
            with self.subTest(route=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)
                self.assertIn(reverse("core:portal_select"), response["Location"])

    def test_librarians_cannot_open_student_pages(self):
        self.client.force_login(make_librarian())
        for name, kwargs in self.STUDENT_ROUTES:
            with self.subTest(route=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 302)

    def test_students_cannot_use_staff_only_post_actions(self):
        user, _ = make_student(username="plain.student")
        self.client.force_login(user)
        response = self.client.post(reverse("core:librarian_book_delete", args=[1]))
        self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse("core:librarian_student_toggle", args=[1]))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_sends_each_role_to_the_right_place(self):
        student_user, _ = make_student()
        self.client.force_login(student_user)
        self.assertRedirects(self.client.get(reverse("core:dashboard")),
                             reverse("core:student"))
        self.client.force_login(make_librarian())
        self.assertRedirects(self.client.get(reverse("core:dashboard")),
                             reverse("core:librarian"))


class ProfileTests(TestCase):
    def setUp(self):
        self.user, self.profile = make_student(
            username="maya.rao", first_name="Maya", last_name="Rao")
        self.client.force_login(self.user)

    def test_profile_page_shows_authenticated_identity(self):
        response = self.client.get(reverse("core:student_profile"))
        self.assertContains(response, "Maya Rao")
        self.assertContains(response, self.profile.student_id)

    def test_student_can_update_own_profile_fields(self):
        response = self.client.post(reverse("core:student_profile_update"), {
            "first_name": "Maya", "last_name": "Rao-Kumar", "email": "maya@college.test",
            "department": "Information Technology", "semester": 6, "phone": "9111111111",
            "enrollment_year": 2023,
        })
        self.assertRedirects(response, reverse("core:student_profile"))
        self.profile.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.profile.department, "Information Technology")
        self.assertEqual(self.user.last_name, "Rao-Kumar")
        self.assertEqual(self.user.email, "maya@college.test")

    def test_password_change_flow_uses_django_authentication(self):
        response = self.client.post(reverse("core:student_password"), {
            "old_password": "test-pass-4321",
            "new_password1": "Fresh-Password-99",
            "new_password2": "Fresh-Password-99",
        })
        self.assertRedirects(response, reverse("core:student_password_done"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Fresh-Password-99"))

    def test_password_change_rejects_wrong_current_password(self):
        response = self.client.post(reverse("core:student_password"), {
            "old_password": "not-my-password",
            "new_password1": "Fresh-Password-99",
            "new_password2": "Fresh-Password-99",
        })
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("test-pass-4321"))
