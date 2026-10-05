"""Shared object factories so each test only states what it cares about."""

from django.contrib.auth import get_user_model

from core.models import (Author, Book, BookCopy, Category, DigitalMaterial,
                         StudentProfile)

User = get_user_model()

_counter = {"n": 0}


def next_id(prefix="X"):
    _counter["n"] += 1
    return f"{prefix}{_counter['n']:05d}"


def make_user(username=None, password="test-pass-4321", **kwargs):
    username = username or next_id("user")
    kwargs.setdefault("first_name", "Test")
    kwargs.setdefault("last_name", "User")
    return User.objects.create_user(username=username, password=password, **kwargs)


def make_student(username=None, password="test-pass-4321", email=None, **kwargs):
    """Create a student.

    Name and email keywords describe the Django user; everything else is
    written to the StudentProfile row.
    """
    user_kwargs = kwargs.pop("user_kwargs", {})
    for name_field in ("first_name", "last_name"):
        if name_field in kwargs:
            user_kwargs[name_field] = kwargs.pop(name_field)
    if email:
        user_kwargs["email"] = email
    user = make_user(username, password, **user_kwargs)
    profile_kwargs = kwargs
    profile = StudentProfile.objects.create(
        user=user,
        student_id=profile_kwargs.pop("student_id", next_id("STU-")),
        department=profile_kwargs.pop("department", "Computer Science"),
        **profile_kwargs)
    return user, profile


def make_librarian(username=None, password="test-pass-4321"):
    return make_user(username, password, is_staff=True, first_name="Library",
                     last_name="Administrator")


def make_book(title=None, isbn=None, copies=1, authors=(), category=None, **kwargs):
    title = title or f"Test Title {next_id('')}"
    book = Book.objects.create(
        title=title, isbn=isbn or next_id("978"), **kwargs)
    for name in authors:
        author, _ = Author.objects.get_or_create(name=name)
        book.authors.add(author)
    if category:
        cat, _ = Category.objects.get_or_create(
            slug=category, defaults={"name": category.replace("-", " ").title()})
        book.categories.add(cat)
    for index in range(copies):
        BookCopy.objects.create(
            book=book, accession_number=next_id("ACC-"),
            status=BookCopy.Status.AVAILABLE)
    return book


def make_material(title=None, **kwargs):
    return DigitalMaterial.objects.create(
        title=title or f"Test Material {next_id('')}",
        external_url=kwargs.pop("external_url", "https://example.edu/resource"),
        **kwargs)
