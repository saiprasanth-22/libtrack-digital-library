"""Catalogue search, filtering, sorting, pagination and book detail."""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Book, BookCopy, Category, DigitalMaterial

from .factories import make_book, make_material, make_student


class SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dbms = make_book(title="Database System Concepts", isbn="9780078022159",
                             authors=("A. Silberschatz",), category="data-systems")
        cls.ddia = make_book(title="Designing Data-Intensive Applications",
                             isbn="9781449373320", authors=("Martin Kleppmann",),
                             category="data-systems")
        cls.ais = make_book(title="Artificial Intelligence: A Modern Approach",
                            isbn="9780134610993", authors=("Stuart Russell",),
                            category="artificial-intelligence")

    def get(self, **params):
        return self.client.get(reverse("core:discover"), params)

    def setUp(self):
        user, _ = make_student()
        self.client.force_login(user)

    def test_landing_page_lists_database_titles_only(self):
        response = self.get(q="Database")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Database System Concepts")
        self.assertNotContains(response, "Designing Data-Intensive Applications")

    def test_search_matches_author(self):
        response = self.get(q="Kleppmann")
        self.assertContains(response, "Designing Data-Intensive Applications")
        self.assertNotContains(response, "Database System Concepts")

    def test_search_matches_isbn(self):
        response = self.get(q="9780134610993")
        self.assertContains(response, "Artificial Intelligence: A Modern Approach")
        self.assertNotContains(response, "Database System Concepts")

    def test_search_matches_category(self):
        response = self.get(q="artificial")
        self.assertContains(response, "Artificial Intelligence: A Modern Approach")

    def test_search_with_no_match_shows_empty_state(self):
        response = self.get(q="zzzz-no-such-book")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No titles matched")

    def test_filter_by_category(self):
        category = Category.objects.get(slug="data-systems")
        response = self.get(category=category.pk)
        self.assertContains(response, "Database System Concepts")
        self.assertContains(response, "Designing Data-Intensive Applications")
        self.assertNotContains(response, "Artificial Intelligence: A Modern Approach")

    def test_filter_by_availability(self):
        BookCopy.objects.filter(book=self.ddia).update(status=BookCopy.Status.ON_LOAN)
        response = self.get(availability="available")
        self.assertContains(response, "Database System Concepts")
        self.assertNotContains(response, "Designing Data-Intensive Applications")

        response = self.get(availability="unavailable")
        self.assertContains(response, "Designing Data-Intensive Applications")
        self.assertNotContains(response, "Database System Concepts")

    def test_sort_by_title_and_newest(self):
        titles_alpha = [b.title for b in
                        self.get(sort="title").context["books"]]
        self.assertEqual(titles_alpha, sorted(titles_alpha))

        newest = [b.title for b in self.get(sort="newest").context["books"]]
        self.assertEqual(len(newest), 3)

    def test_pagination_splits_results(self):
        with self.settings(LIBRARY_RULES={**self.settings_dict(), "PAGE_SIZE": 2}):
            response = self.get()
            self.assertEqual(len(response.context["books"]), 2)
            self.assertEqual(response.context["total_results"], 3)
            self.assertTrue(response.context["page_obj"].has_next())

    def test_pagination_preserves_query_parameters(self):
        with self.settings(LIBRARY_RULES={**self.settings_dict(), "PAGE_SIZE": 2}):
            response = self.get(q="a", sort="title")
            self.assertEqual(response.status_code, 200)
            self.assertIn("q=a", response.context["request"].META["QUERY_STRING"])

    @staticmethod
    def settings_dict():
        from django.conf import settings as dj
        return dj.LIBRARY_RULES


class BookDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.book = make_book(title="Database System Concepts", isbn="9780078022159",
                             copies=3, authors=("A. Silberschatz",),
                             category="data-systems", publisher="McGraw Hill",
                             publication_year=2019, edition="7th",
                             description="Foundations of database management.")

    def setUp(self):
        user, _ = make_student()
        self.client.force_login(user)

    def test_detail_shows_bibliographic_fields_and_live_availability(self):
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "9780078022159")
        self.assertContains(response, "McGraw Hill")
        self.assertContains(response, "Foundations of database management.")
        self.assertContains(response, "A. Silberschatz")
        self.assertContains(response, "3 of 3 copies")

    def test_availability_label_reflects_database_state(self):
        pks = list(self.book.copies.values_list("pk", flat=True)[:2])
        BookCopy.objects.filter(pk__in=pks).update(status=BookCopy.Status.ON_LOAN)
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertContains(response, "1 of 3 copies")

        BookCopy.objects.filter(book=self.book).update(status=BookCopy.Status.ON_LOAN)
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertContains(response, "Currently on loan")

    def test_unknown_slug_returns_404(self):
        response = self.client.get(reverse("core:book_detail", args=["no-such-book"]))
        self.assertEqual(response.status_code, 404)

    def test_inactive_book_is_not_public(self):
        self.book.is_active = False
        self.book.save(update_fields=["is_active"])
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertEqual(response.status_code, 404)

    def test_slug_is_generated_and_stays_unique(self):
        twin = Book.objects.create(title="Database System Concepts")
        self.assertNotEqual(twin.slug, self.book.slug)
        self.assertTrue(twin.slug.startswith("database-system-concepts"))

    def test_cover_variant_is_stable_and_uses_designed_artwork(self):
        from django.conf import settings as dj
        self.assertIn(self.book.cover_variant, dj.LIBRARY_COVER_VARIANTS)
        self.assertEqual(self.book.cover_variant,
                         Book.objects.get(pk=self.book.pk).cover_variant)

    def test_anonymous_visitor_is_prompted_to_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertRedirects(response, reverse("core:portal_select") +
                             f"?next=/books/{self.book.slug}/", fetch_redirect_response=False)


class DigitalMaterialTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.book = make_book(title="Database System Concepts")
        cls.public = make_material(title="Relational Design Notes")
        cls.hidden = make_material(title="Internal Guide", is_public=False)
        cls.linked = make_material(title="Linked Notes", book=cls.book)

    def setUp(self):
        user, _ = make_student()
        self.client.force_login(user)

    def test_public_materials_are_listed(self):
        response = self.client.get(reverse("core:materials"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Relational Design Notes")
        self.assertNotContains(response, "Internal Guide")

    def test_material_search_filters_results(self):
        response = self.client.get(reverse("core:materials"), {"q": "Relational"})
        self.assertContains(response, "Relational Design Notes")
        self.assertNotContains(response, "Linked Notes")

    def test_linked_material_appears_on_its_book_page(self):
        response = self.client.get(reverse("core:book_detail", args=[self.book.slug]))
        self.assertContains(response, "Linked Notes")
        self.assertNotContains(response, "Internal Guide")

    def test_external_link_is_rendered_with_safe_rel_attributes(self):
        response = self.client.get(reverse("core:materials"))
        self.assertContains(response, 'rel="noopener noreferrer"')
        self.assertNotContains(response, "http://example.edu")


class BookCreationValidationTests(TestCase):
    """Inventory and catalogue rules enforced above the template layer."""

    def test_negative_copy_count_is_rejected_by_the_form(self):
        from core.forms import BookForm
        form = BookForm(data={"title": "Bad Inventory", "total_copies": -3})
        self.assertFalse(form.is_valid())
        self.assertIn("total_copies", form.errors)

    def test_non_numeric_isbn_is_rejected(self):
        from core.forms import BookForm
        form = BookForm(data={"title": "Bad ISBN", "isbn": "not-an-isbn",
                              "total_copies": 1})
        self.assertFalse(form.is_valid())
        self.assertIn("isbn", form.errors)

    def test_duplicate_isbn_is_rejected_by_the_unique_constraint(self):
        from core.forms import BookForm
        make_book(isbn="9780078022159")
        form = BookForm(data={"title": "Clash", "isbn": "9780078022159",
                              "total_copies": 1})
        self.assertFalse(form.is_valid())
        self.assertIn("isbn", form.errors)

    def test_oversized_cover_upload_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.forms import BookForm
        big = SimpleUploadedFile("cover.png", b"0" * (5 * 1024 * 1024),
                                 content_type="image/png")
        form = BookForm(data={"title": "Big Cover", "total_copies": 1}, files={"cover": big})
        self.assertFalse(form.is_valid())
        self.assertIn("cover", form.errors)

    def test_material_requires_a_file_or_a_url(self):
        from core.forms import DigitalMaterialForm
        form = DigitalMaterialForm(data={"title": "No Source"})
        self.assertFalse(form.is_valid())
        self.assertIn("Attach a file or provide an external URL",
                      str(form.non_field_errors()))

    def test_material_rejects_disallowed_file_extension(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from core.forms import DigitalMaterialForm
        payload = SimpleUploadedFile("payload.exe", b"MZ", content_type="application/exe")
        form = DigitalMaterialForm(data={"title": "Bad File"}, files={"file": payload})
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)
