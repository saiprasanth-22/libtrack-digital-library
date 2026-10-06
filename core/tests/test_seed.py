"""The demo data command must be safe to run more than once."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from django.contrib.auth import get_user_model

from core.models import (Author, Book, BookCopy, Category, DigitalMaterial, Loan,
                         StudentProfile)

User = get_user_model()
from core.models import ActivityLog


def counts():
    return {
        "books": Book.objects.count(),
        "copies": BookCopy.objects.count(),
        "categories": Category.objects.count(),
        "authors": Author.objects.count(),
        "materials": DigitalMaterial.objects.count(),
        "students": StudentProfile.objects.count(),
        "loans": Loan.objects.count(),
    }


class SeedDemoDataTests(TestCase):
    def seed(self):
        call_command("seed_demo_data", password="demo-password-123",
                     stdout=StringIO(), stderr=StringIO())

    def test_seed_creates_the_expected_dataset(self):
        self.seed()
        self.assertGreaterEqual(Book.objects.count(), 12)
        self.assertGreaterEqual(Category.objects.count(), 3)
        self.assertGreaterEqual(Author.objects.count(), 3)
        self.assertGreaterEqual(DigitalMaterial.objects.count(), 3)
        self.assertEqual(StudentProfile.objects.count(), 3)

    def test_seed_creates_a_student_and_a_librarian(self):
        self.seed()
        student = StudentProfile.objects.get(student_id="LT260001")
        self.assertEqual(student.display_name, "Maya Rao")
        self.assertTrue(student.user.is_staff is False)

        librarian = User.objects.get(username="library.admin")
        self.assertTrue(librarian.is_staff)
        self.assertEqual(librarian.get_full_name(), "Library Administrator")
        self.assertFalse(
            StudentProfile.objects.filter(user__username="library.admin").exists(),
            "staff accounts must not also be student profiles")

    def test_seed_creates_a_mixture_of_loan_states(self):
        self.seed()
        statuses = set(Loan.objects.values_list("status", flat=True))
        self.assertIn(Loan.Status.ISSUED, statuses)
        self.assertIn(Loan.Status.RETURNED, statuses)
        self.assertIn(Loan.Status.OVERDUE, statuses)
        self.assertIn(Loan.Status.REQUESTED, statuses)

    def test_seeded_materials_use_real_resource_urls(self):
        self.seed()
        self.assertFalse(DigitalMaterial.objects.filter(
            external_url__icontains="example.edu").exists())

    def test_running_the_command_twice_creates_no_duplicates(self):
        self.seed()
        first = counts()
        self.seed()
        second = counts()
        self.assertEqual(first, second)

    def test_rerun_does_not_reset_a_changed_password(self):
        self.seed()
        user = StudentProfile.objects.get(student_id="LT260001").user
        user.set_password("Operator-Chosen-Password")
        user.save(update_fields=["password"])
        self.seed()
        user.refresh_from_db()
        self.assertTrue(user.check_password("Operator-Chosen-Password"))

    def test_seeded_copies_match_their_loan_records(self):
        self.seed()
        for loan in Loan.objects.filter(copy__isnull=False):
            if loan.status in Loan.ON_LOAN_STATUSES:
                self.assertEqual(loan.copy.status, BookCopy.Status.ON_LOAN)
            else:
                self.assertNotEqual(loan.copy.status, BookCopy.Status.ON_LOAN)

    def test_alias_command_still_runs(self):
        call_command("seed_library", password="demo-password-123",
                     stdout=StringIO(), stderr=StringIO())
        self.assertGreaterEqual(Book.objects.count(), 12)
