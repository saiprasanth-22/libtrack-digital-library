"""Create a repeatable LibTrack demo catalogue and accounts."""

import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (Author, Book, BookCopy, Category, DigitalMaterial,
                         Loan, StudentProfile, Subject)


class Command(BaseCommand):
    help = "Seed demo users, academic catalogue records, copies, materials and loans."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=os.getenv("LIBTRACK_DEMO_PASSWORD", "LibTrackDemo2026!"),
                            help="Password assigned only to newly-created demo accounts.")
        parser.add_argument("--students", type=int, default=3, help="Number of demo students to create (1–20).")

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        student_count = options["students"]
        if not 1 <= student_count <= 20:
            self.stderr.write(self.style.ERROR("--students must be between 1 and 20"))
            return
        User = get_user_model()
        librarian, made = User.objects.get_or_create(
            username="demo.librarian",
            defaults={"email": "librarian@libtrack.demo", "first_name": "Asha", "last_name": "Menon",
                      "is_staff": True, "is_active": True},
        )
        self._set_password_if_new(librarian, made, password)
        librarian.is_staff = True
        librarian.save(update_fields=["is_staff"])

        students = []
        sample_students = [
            ("demo.student", "Demo", "Student", "CS", 4),
            ("demo.student2", "Mira", "Rao", "Electronics", 6),
            ("demo.student3", "Arjun", "Kumar", "Mechanical", 3),
        ]
        for index, (username, first, last, department, semester) in enumerate(sample_students[:student_count], 1):
            user, made = User.objects.get_or_create(username=username, defaults={
                "email": f"{username.replace('.', '')}@libtrack.demo",
                "first_name": first, "last_name": last, "is_active": True,
            })
            self._set_password_if_new(user, made, password)
            if user.first_name != first or user.last_name != last:
                user.first_name, user.last_name = first, last
                user.save(update_fields=["first_name", "last_name"])
            profile, _ = StudentProfile.objects.get_or_create(user=user, defaults={
                "student_id": f"LT2026{index:03d}", "department": department,
                "semester": semester, "enrollment_year": 2024,
            })
            students.append(profile)

        categories = {}
        for name, slug in (("Computer Science", "computer-science"), ("Data Systems", "data-systems"),
                           ("Software Engineering", "software-engineering"), ("Artificial Intelligence", "artificial-intelligence")):
            categories[name], _ = Category.objects.get_or_create(slug=slug, defaults={"name": name})
        subjects = {}
        for name, code in (("Computer Science", "CS"), ("Information Technology", "IT"), ("Electronics", "EC")):
            subjects[name], _ = Subject.objects.get_or_create(code=code, defaults={"name": name})
        authors = {}
        for name in ("A. Silberschatz", "Henry F. Korth", "S. Sudarshan", "Martin Kleppmann",
                     "Andrew Hunt", "David Thomas", "Stuart Russell", "Peter Norvig"):
            authors[name], _ = Author.objects.get_or_create(name=name)

        books = [
            {"title": "Database System Concepts", "isbn": "9780078022159", "publisher": "McGraw Hill",
             "publication_year": 2019, "edition": "7th", "page_count": 1376, "subject": "Computer Science",
             "authors": ("A. Silberschatz", "Henry F. Korth", "S. Sudarshan"), "categories": ("Computer Science", "Data Systems"), "copies": 4},
            {"title": "Designing Data-Intensive Applications", "isbn": "9781449373320", "publisher": "O'Reilly Media",
             "publication_year": 2017, "edition": "1st", "page_count": 616, "subject": "Information Technology",
             "authors": ("Martin Kleppmann",), "categories": ("Computer Science", "Data Systems"), "copies": 3},
            {"title": "The Pragmatic Programmer", "isbn": "9780135957059", "publisher": "Addison-Wesley",
             "publication_year": 2019, "edition": "20th Anniversary", "page_count": 352, "subject": "Computer Science",
             "authors": ("Andrew Hunt", "David Thomas"), "categories": ("Software Engineering",), "copies": 3},
            {"title": "Artificial Intelligence: A Modern Approach", "isbn": "9780134610993", "publisher": "Pearson",
             "publication_year": 2020, "edition": "4th", "page_count": 1152, "subject": "Computer Science",
             "authors": ("Stuart Russell", "Peter Norvig"), "categories": ("Computer Science", "Artificial Intelligence"), "copies": 2},
        ]
        catalog = []
        for entry in books:
            book, _ = Book.objects.get_or_create(isbn=entry["isbn"], defaults={
                "title": entry["title"], "publisher": entry["publisher"],
                "publication_year": entry["publication_year"], "edition": entry["edition"],
                "page_count": entry["page_count"], "subject": subjects[entry["subject"]],
                "description": f"A widely used academic reference covering {entry['title'].lower()}.",
                "language": "English", "is_active": True,
            })
            if not book.subject_id:
                book.subject = subjects[entry["subject"]]
                book.save(update_fields=["subject", "updated_at"])
            book.authors.add(*(authors[name] for name in entry["authors"]))
            book.categories.add(*(categories[name] for name in entry["categories"]))
            catalog.append(book)
            for copy_number in range(1, entry["copies"] + 1):
                BookCopy.objects.get_or_create(
                    accession_number=f"LIB-{entry['isbn'][-6:]}-{copy_number:02d}",
                    defaults={"book": book, "status": BookCopy.Status.AVAILABLE,
                              "shelf_location": f"CS-{copy_number:02d}"},
                )

        materials = [
            ("Introduction to Relational Database Design", DigitalMaterial.MaterialType.NOTES, "Computer Science", "https://example.edu/resources/relational-design.pdf"),
            ("A Survey of Modern Database Systems", DigitalMaterial.MaterialType.PAPER, "Information Technology", "https://example.edu/papers/modern-databases"),
            ("Foundations of Artificial Intelligence", DigitalMaterial.MaterialType.EBOOK, "Computer Science", "https://example.edu/resources/ai-foundations"),
        ]
        for title, material_type, subject_name, url in materials:
            material, _ = DigitalMaterial.objects.get_or_create(title=title, defaults={
                "material_type": material_type, "subject": subjects[subject_name],
                "description": f"Curated academic resource: {title}.",
                "external_url": url, "is_active": True,
            })
            material.categories.add(categories["Computer Science"])

        # A small set of loans makes the dashboard useful on first run. Existing
        # loan history is never reset or duplicated by subsequent seed runs.
        now = timezone.now()
        if students and catalog:
            sample_copy = catalog[0].copies.order_by("accession_number").first()
            if sample_copy and not Loan.objects.filter(copy=sample_copy,
                    status__in=(Loan.Status.ISSUED, Loan.Status.OVERDUE)).exists():
                Loan.objects.create(student=students[0], copy=sample_copy,
                    issued_at=now - timedelta(days=4), due_at=now + timedelta(days=10),
                    status=Loan.Status.ISSUED, issued_by=librarian)
                sample_copy.status = BookCopy.Status.ON_LOAN
                sample_copy.save(update_fields=["status", "updated_at"])
        if len(students) > 1 and len(catalog) > 1:
            past_copy = catalog[1].copies.order_by("accession_number").first()
            if past_copy and not Loan.objects.filter(copy=past_copy, student=students[1]).exists():
                Loan.objects.create(student=students[1], copy=past_copy,
                    issued_at=now - timedelta(days=35), due_at=now - timedelta(days=7),
                    status=Loan.Status.OVERDUE, issued_by=librarian,
                    fine_amount="70.00")
                past_copy.status = BookCopy.Status.ON_LOAN
                past_copy.save(update_fields=["status", "updated_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(catalog)} books, {DigitalMaterial.objects.count()} digital materials, "
            f"{len(students)} students and a librarian. Newly created demo accounts use: {password}"
        ))

    @staticmethod
    def _set_password_if_new(user, created, password):
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
