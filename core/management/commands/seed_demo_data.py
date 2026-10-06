"""Populate the database with a realistic, repeatable demonstration dataset.

Running the command twice does not create duplicates: every record is looked up
by a natural key (ISBN, slug, name, accession number) before being created, and
borrowing history is only seeded when it is missing.

    python manage.py seed_demo_data
"""

import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (Author, Book, BookCopy, Category, DigitalMaterial, Loan,
                         ReadingList, Subject, StudentProfile)

User = get_user_model()

CATEGORIES = [
    ("Computer Science", "computer-science",
     "Programming, software construction and computing theory."),
    ("Data Systems", "data-systems",
     "Databases, distributed systems and large-scale data engineering."),
    ("Artificial Intelligence", "artificial-intelligence",
     "Machine learning, reasoning and intelligent agents."),
    ("Software Engineering", "software-engineering",
     "Process, architecture, testing and project practice."),
    ("Electronics", "electronics",
     "Circuits, embedded systems, signals and communication."),
]

SUBJECTS = [
    ("Computer Science", "CS"),
    ("Information Technology", "IT"),
    ("Electronics", "EC"),
    ("Mathematics", "MA"),
]

AUTHORS = [
    ("A. Silberschatz", "Professor of computer science and co-author of the "
     "standard database systems textbook."),
    ("Henry F. Korth", "Database systems researcher and professor."),
    ("S. Sudarshan", "Compiler and database systems researcher."),
    ("Martin Kleppmann", "Distributed systems engineer and author."),
    ("Andrew Hunt", "Software engineer and co-author of The Pragmatic Programmer."),
    ("David Thomas", "Software engineer and co-author of The Pragmatic Programmer."),
    ("Stuart Russell", "Professor of computer science and co-author of AIMA."),
    ("Peter Norvig", "Computer scientist and co-author of Artificial Intelligence."),
    ("Thomas H. Cormen", "Professor of computer science and co-author of Introduction to Algorithms."),
    ("Charles E. Leiserson", "Professor of computer science."),
    ("Bjarne Stroustrup", "Designer of the C++ programming language."),
    ("James F. Kurose", "Computer networking researcher and author."),
    ("David W. Balakumar", "Electronics and embedded systems educator."),
    ("Ramesh Chandra", "Firmware and embedded systems researcher."),
    ("Robert C. Martin", "Software architect and author on clean architecture."),
    ("Kenneth H. Rosen", "Discrete mathematics educator and author."),
    ("Joe Reis", "Data platform engineer and author."),
    ("Charity Majors", "Data platform engineer and author."),
    ("John P. Hayes", "Computer architecture educator and author."),
    ("Roger S. Pressman", "Software engineering educator and author."),
    ("Bruce Maxim", "Software engineering educator and author."),
]

# title, isbn, publisher, year, edition, pages, subject, authors, category, copies, featured
BOOKS = [
    ("Database System Concepts", "9780078022159", "McGraw Hill", 2019, "7th", 1376,
     "Computer Science", ("A. Silberschatz", "Henry F. Korth", "S. Sudarshan"),
     "Data Systems", 5, True),
    ("Designing Data-Intensive Applications", "9781449373320", "O'Reilly Media", 2017,
     "1st", 616, "Information Technology", ("Martin Kleppmann",),
     "Data Systems", 4, True),
    ("The Pragmatic Programmer", "9780135957059", "Addison-Wesley", 2019,
     "20th Anniversary", 352, "Computer Science", ("Andrew Hunt", "David Thomas"),
     "Software Engineering", 4, False),
    ("Introduction to Algorithms", "9780262046305", "MIT Press", 2022,
     "4th", 1312, "Computer Science",
     ("Thomas H. Cormen", "Charles E. Leiserson"), "Computer Science", 3, True),
    ("Artificial Intelligence: A Modern Approach", "9780134610993", "Pearson", 2020,
     "4th", 1152, "Computer Science", ("Stuart Russell", "Peter Norvig"),
     "Artificial Intelligence", 3, False),
    ("The C++ Programming Language", "9780321953820", "Addison-Wesley", 2018,
     "4th", 1216, "Computer Science", ("Bjarne Stroustrup",),
     "Computer Science", 2, False),
    ("Computer Networking: A Top-Down Approach", "9780132126953", "Pearson", 2021,
     "8th", 896, "Information Technology", ("James F. Kurose",),
     "Electronics", 3, False),
    ("Digital Design and Computer Architecture", "9780128180644", "Elsevier", 2021,
     "2nd", 656, "Electronics", ("Ramesh Chandra", "Bjarne Stroustrup"),
     "Electronics", 2, False),
    ("Operating System Concepts", "9781118063330", "Wiley", 2018, "10th", 944,
     "Computer Science", ("A. Silberschatz", "Peter Norvig"),
     "Computer Science", 3, False),
    ("Clean Architecture: A Craftsman's Guide", "9780134494166", "Prentice Hall", 2017,
     "1st", 342, "Information Technology", ("Robert C. Martin",),
     "Software Engineering", 2, False),
    ("Discrete Mathematics and Its Applications", "9780036783031", "Cengage", 2019,
     "8th", 1064, "Mathematics", ("Kenneth H. Rosen",), "Computer Science", 2, False),
    ("Fundamentals of Data Engineering", "9781098119062", "O'Reilly Media", 2022,
     "1st", 480, "Information Technology", ("Joe Reis", "Charity Majors"),
     "Data Systems", 3, False),
    ("Computer Architecture and Organization", "9780128200643", "Morgan Kaufmann", 2020,
     "4th", 544, "Electronics", ("John P. Hayes",), "Electronics", 2, False),
    ("Software Engineering: A Practitioner's Approach", "9780073371217", "McGraw Hill", 2019,
     "9th", 800, "Computer Science", ("Roger S. Pressman", "Bruce Maxim"),
     "Software Engineering", 2, False),
]

DESCRIPTIONS = {
    "Database System Concepts": (
        "The reference text for database management systems. It walks from the "
        "relational model and SQL through storage, indexing, query processing, "
        "transaction management and distributed databases, linking each idea to "
        "the decisions engineers actually make."),
    "Designing Data-Intensive Applications": (
        "Explores the trade-offs behind reliable, scalable and maintainable "
        "systems through replication, partitioning, transactions and stream "
        "processing, with a strong focus on the data models that underlie them."),
    "The Pragmatic Programmer": (
        "A practical handbook on software craft: requirements, estimation, "
        "testing, refactoring and the habits that let small teams ship software "
        "that other people can keep working on."),
    "Introduction to Algorithms": (
        "A broad, rigorous survey of classic algorithms and data structures with "
        "an emphasis on proofs of correctness, complexity analysis and practical "
        "implementations."),
    "Artificial Intelligence: A Modern Approach": (
        "Surveys intelligent agents, search, constraint satisfaction, knowledge "
        "representation, planning, learning and reinforcement learning."),
    "The C++ Programming Language": (
        "A complete description of modern C++ covering the standard library, "
        "object model, templates, concurrency and move semantics."),
    "Computer Networking: A Top-Down Approach": (
        "Builds networking knowledge from the application layer downwards, "
        "covering transport, routing, link layers and security with worked "
        "problems at every level."),
    "Digital Design and Computer Architecture": (
        "Combines digital logic design with computer organisation, covering "
        "combinational and sequential circuits, pipelining, memory hierarchy and "
        "embedded implementation."),
    "Operating System Concepts": (
        "Describes operating system structure, processes, threads, scheduling, "
        "synchronisation, memory management and file systems with worked "
        "examples of how each subsystem actually works."),
    "Clean Architecture: A Craftsman's Guide": (
        "Argues for business rules that do not depend on the delivery mechanism, "
        "with practical guidance on boundaries, dependency direction and test "
        "design."),
    "Discrete Mathematics and Its Applications": (
        "Covers logic, proof techniques, sets, relations, combinatorics, graph "
        "theory and elementary number theory with an emphasis on problem solving."),
    "Fundamentals of Data Engineering": (
        "A practical guide to building reliable data platforms: storage formats, "
        "batch and streaming processing, data quality, observability and "
        "ownership."),
    "Computer Architecture and Organization": (
        "Introduces instruction sets, pipelining, memory systems, parallelism "
        "and performance measurement at an undergraduate engineering level."),
    "Software Engineering: A Practitioner's Approach": (
        "Covers process, modelling, design, implementation, testing, maintenance "
        "and project management with an emphasis on real engineering practice."),
}

MATERIALS = [
    ("Relational Design and Normalisation Notes", DigitalMaterial.MaterialType.NOTES,
     "Data Systems", "Step-by-step normalisation worked examples used in the DBMS unit.",
     "https://www.db-book.com/slides-dir/PDF-dir/ch7.pdf", True),
    ("Transaction Management Cheat Sheet", DigitalMaterial.MaterialType.NOTES,
     "Data Systems", "Isolation levels, lock granularity and commit protocols on two pages.",
     "https://www.postgresql.org/docs/current/mvcc.html", True),
    ("A Survey of Modern Database Systems", DigitalMaterial.MaterialType.PAPER,
     "Data Systems", "Comparative study of row-store and column-store engines.",
     "https://15445.courses.cs.cmu.edu/fall2024/", True),
    ("Foundations of Machine Learning", DigitalMaterial.MaterialType.EBOOK,
     "Artificial Intelligence", "Introductory companion notes for the AI course sequence.",
     "https://developers.google.com/machine-learning/crash-course", True),
    ("Indexing Strategies Reference", DigitalMaterial.MaterialType.PAPER,
     "Computer Science", "B-tree, hash and inverted index selection guidance.",
     "https://www.postgresql.org/docs/current/indexes.html", True),
    ("Internal Testing Resource", DigitalMaterial.MaterialType.OTHER,
     "Software Engineering", "Visibility check: this material is not public.",
     "https://martinfowler.com/testing/", False),
]

# Demo identities are deliberately neutral placeholders, not real people.
DEMO_STUDENT = ("student", "Student", "User", "Computer Science", 5)
DEMO_STUDENTS = [
    DEMO_STUDENT,
    ("arjun.nair", "Arjun", "Nair", "Electronics", 3),
    ("leela.venkat", "Leela", "Venkat", "Information Technology", 7),
]
LIBRARIAN = ("admin", "Library", "Administrator")


class Command(BaseCommand):
    help = "Seed categories, authors, books, copies, materials, demo accounts and loan history."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password", default=os.getenv("LIBTRACK_DEMO_PASSWORD", "1"),
            help="Password applied only to demo accounts that are created by this run.")
        parser.add_argument(
            "--students", type=int, default=len(DEMO_STUDENTS),
            help="How many demo students to create (0-%d)." % len(DEMO_STUDENTS))

    @transaction.atomic
    def handle(self, *args, **options):
        password = options["password"]
        student_count = max(0, min(options["students"], len(DEMO_STUDENTS)))
        now = timezone.now()

        categories = self._seed_categories()
        subjects = self._seed_subjects()
        authors = self._seed_authors()

        librarian = self._ensure_user(
            LIBRARIAN[0], LIBRARIAN[1], LIBRARIAN[2], "librarian@libtrack.demo",
            password, is_staff=True)
        students = [self._ensure_student(entry, index, password)
                    for index, entry in enumerate(DEMO_STUDENTS[:student_count], start=1)]

        catalog = self._seed_books(authors, categories, subjects)
        self._seed_materials(categories, subjects, catalog)
        self._seed_loans(catalog, students, librarian, now)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(categories)} categories, {len(authors)} authors, {len(catalog)} books, "
            f"{BookCopy.objects.count()} copies, {DigitalMaterial.objects.count()} materials and "
            f"{len(students)} students."
        ))
        self.stdout.write("Demo accounts (local use only):")
        for user in [librarian] + [profile.user for profile in students]:
            self.stdout.write(f"  {user.username} / {user.first_name} {user.last_name}")

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _ensure_user(username, first, last, email, password, *, is_staff=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "first_name": first, "last_name": last,
                      "is_staff": is_staff, "is_active": True})
        if created:
            user.set_password(password)
            user.save(update_fields=["password"])
        elif user.first_name != first or user.last_name != last:
            # Keep the display name current without ever resetting a password
            # that an operator may have changed since the last run.
            user.first_name, user.last_name = first, last
            user.save(update_fields=["first_name", "last_name"])
        return user

    def _ensure_student(self, entry, index, password):
        username, first, last, department, semester = entry
        user = self._ensure_user(
            username, first, last, f"{username.replace('.', '_')}@student.libtrack.demo",
            password)
        profile, created = StudentProfile.objects.get_or_create(
            user=user,
            defaults={"student_id": f"LT26{index:04d}", "department": department,
                      "semester": semester, "enrollment_year": 2024, "is_active": True})
        if created:
            ReadingList.objects.create(
                student=profile, name="My reading list", is_default=True)
        return profile

    @staticmethod
    def _seed_categories():
        result = {}
        for name, slug, description in CATEGORIES:
            category, _ = Category.objects.get_or_create(
                slug=slug, defaults={"name": name, "description": description})
            result[name] = category
        return result

    @staticmethod
    def _seed_subjects():
        result = {}
        for name, code in SUBJECTS:
            subject, _ = Subject.objects.get_or_create(
                code=code, defaults={"name": name})
            result[name] = subject
        return result

    @staticmethod
    def _seed_authors():
        result = {}
        for name, biography in AUTHORS:
            author, _ = Author.objects.get_or_create(
                name=name, defaults={"biography": biography})
            result[name] = author
        return result

    @staticmethod
    def _seed_books(authors, categories, subjects):
        catalog = []
        for (title, isbn, publisher, year, edition, pages, subject_name,
             author_names, category_name, copies, featured) in BOOKS:
            book, _ = Book.objects.get_or_create(
                isbn=isbn,
                defaults={
                    "title": title,
                    "publisher": publisher,
                    "publication_year": year,
                    "edition": edition,
                    "page_count": pages,
                    "subject": subjects[subject_name],
                    "description": DESCRIPTIONS.get(title, f"An academic title in the LibTrack collection: {title}."),
                    "language": "English",
                    "featured": featured,
                    "is_active": True,
                })
            # Every author named by a title must exist, otherwise the book
            # would silently render with no byline.
            missing = [name for name in author_names if name not in authors]
            if missing:
                raise ValueError(
                    "Books reference authors that are not in the AUTHORS list: %s"
                    % ", ".join(missing))
            book.authors.set([authors[name] for name in author_names])
            book.categories.set([categories[category_name]])
            # Top up copies so a fresh run always has a full shelf, without
            # duplicating copies that already exist.
            existing = book.copies.count()
            if existing < copies:
                for index in range(existing + 1, copies + 1):
                    BookCopy.objects.get_or_create(
                        accession_number=f"LT-{isbn[-6:]}-{index:02d}",
                        defaults={"book": book, "status": BookCopy.Status.AVAILABLE,
                                  "shelf_location": f"{subjects[subject_name].code}-{index:02d}"})
            catalog.append(book)
        return catalog

    @staticmethod
    def _seed_materials(categories, subjects, catalog):
        by_title = {book.title: book for book in catalog}
        for (title, material_type, category_name, description, url, is_public) in MATERIALS:
            material, _ = DigitalMaterial.objects.get_or_create(
                title=title,
                defaults={
                    "material_type": material_type,
                    "subject": subjects.get({"Data Systems": "Computer Science",
                                             "Computer Science": "Computer Science",
                                             "Artificial Intelligence": "Computer Science",
                                             "Electronics": "Electronics",
                                             "Information Technology": "Information Technology",
                                             "Software Engineering": "Computer Science",
                                             "Mathematics": "Mathematics"}[category_name]),
                    "description": description,
                    "external_url": url,
                    "is_public": is_public,
                })
            material.categories.set([categories[category_name]])
            if material.external_url != url:
                material.external_url = url
                material.save(update_fields=["external_url", "updated_at"])
            # Attach the first three notes to a related title for the detail page.
            if material.material_type == DigitalMaterial.MaterialType.NOTES and not material.book_id:
                linked = by_title.get("Database System Concepts") or (catalog[0] if catalog else None)
                if linked:
                    material.book = linked
                    material.save(update_fields=["book", "updated_at"])

        # Repair links from an earlier presentation snapshot without creating
        # additional materials that are not part of the current seed dataset.
        legacy_urls = {
            "Introduction to Relational Database Design":
                "https://www.db-book.com/slides-dir/PDF-dir/ch7.pdf",
            "Foundations of Artificial Intelligence":
                "https://inst.eecs.berkeley.edu/~cs188/fa24/",
        }
        for title, url in legacy_urls.items():
            DigitalMaterial.objects.filter(title=title).exclude(
                external_url=url).update(external_url=url)

    @staticmethod
    def _seed_loans(catalog, students, librarian, now):
        """Create a mix of active, returned, overdue and pending records."""
        if not students or not catalog:
            return
        plan = [
            # (book index, student index, days_since_issue, days_of_loan, desired status)
            (0, 0, 4, 14, Loan.Status.ISSUED),
            (3, 0, 40, 14, Loan.Status.RETURNED),
            (1, 1, 30, 14, Loan.Status.OVERDUE),
            (5, 1, 60, 14, Loan.Status.RETURNED),
            (7, 2, 2, 14, Loan.Status.ISSUED),
            (8, 0, 0, 14, Loan.Status.REQUESTED),
        ]
        for book_index, student_index, days_ago, loan_days, status in plan:
            if book_index >= len(catalog) or student_index >= len(students):
                continue
            book = catalog[book_index]
            student = students[student_index]
            issued_at = now - timedelta(days=days_ago)
            due_at = issued_at + timedelta(days=loan_days)

            if Loan.objects.filter(student=student, book=book).exists():
                continue

            if status == Loan.Status.REQUESTED:
                Loan.objects.create(student=student, book=book, status=Loan.Status.REQUESTED,
                                    requested_at=issued_at)
                continue

            copy = (BookCopy.objects.filter(book=book, status=BookCopy.Status.AVAILABLE)
                    .order_by("accession_number").first())
            if copy is None:
                continue

            returned = status == Loan.Status.RETURNED
            loan = Loan.objects.create(
                student=student, book=book, copy=copy, status=status,
                requested_at=issued_at, issued_at=issued_at, due_at=due_at,
                returned_at=(due_at + timedelta(days=2)) if returned else None,
                issued_by=librarian,
                received_by=librarian if returned else None,
                fine_amount="20.00" if returned else 0)
            # `created_at` is auto-set to now, so it is backdated afterwards.
            # Without this the monthly chart and the date-range reports would
            # all pile every record into today.
            Loan.objects.filter(pk=loan.pk).update(
                created_at=issued_at, updated_at=issued_at)

            if status == Loan.Status.OVERDUE:
                loan.status = Loan.Status.OVERDUE
                loan.save(update_fields=["status", "updated_at"])
            if not returned:
                copy.status = BookCopy.Status.ON_LOAN
                copy.save(update_fields=["status", "updated_at"])

            # One extra renewal on the returned title so the history shows the rule working.
            if returned and book_index == 3:
                loan.renewal_count = 1
                loan.save(update_fields=["renewal_count", "updated_at"])
