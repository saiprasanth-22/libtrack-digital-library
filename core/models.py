"""Relational data model for LibTrack.

The schema is deliberately normalised: catalogue metadata is separated from
physical inventory, and every borrowing event is one row in ``Loan`` (the
project's borrow record) that references a student and a book.
"""

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class TimestampedModel(models.Model):
    """Adds creation and modification timestamps to a table."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StudentProfile(TimestampedModel):
    """Extra academic details that hang off a Django ``User`` row."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    student_id = models.CharField(max_length=32, unique=True)
    department = models.CharField(max_length=100, blank=True)
    semester = models.PositiveSmallIntegerField(
        null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(12)])
    phone = models.CharField(max_length=24, blank=True)
    enrollment_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # A librarian can suspend borrowing rights without deleting history.
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["student_id"]
        indexes = [
            models.Index(fields=["department", "semester"], name="student_dept_sem_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(semester__isnull=True)
                | models.Q(semester__gte=1, semester__lte=12),
                name="student_semester_1_to_12"),
        ]

    def __str__(self):
        return f"{self.student_id} — {self.user.get_full_name() or self.user.get_username()}"

    @property
    def display_name(self):
        return self.user.get_full_name() or self.user.get_username()

    @property
    def can_borrow(self):
        """Borrowing needs both a live login and an unsuspended profile."""
        return self.is_active and self.user.is_active


class Author(TimestampedModel):
    name = models.CharField(max_length=160, unique=True)
    biography = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Category(TimestampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=110, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Subject(TimestampedModel):
    name = models.CharField(max_length=120, unique=True)
    code = models.CharField(max_length=24, unique=True, null=True, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class BookQuerySet(models.QuerySet):
    """Reusable catalogue queries shared by the public and staff views."""

    def active(self):
        return self.filter(is_active=True)

    def with_availability(self):
        """Prefetch copies so ``total_copies``/``available_copies`` avoid extra queries."""
        return self.prefetch_related("copies")

    def searchable(self, term):
        """Match the term against title, author, ISBN, publisher and category."""
        if not term:
            return self
        return self.filter(
            models.Q(title__icontains=term)
            | models.Q(subtitle__icontains=term)
            | models.Q(isbn__icontains=term)
            | models.Q(publisher__icontains=term)
            | models.Q(description__icontains=term)
            | models.Q(authors__name__icontains=term)
            | models.Q(categories__name__icontains=term)
            | models.Q(subject__name__icontains=term)
        ).distinct()

    def available_only(self):
        """Keep books that currently have at least one free copy."""
        return self.filter(copies__status=BookCopy.Status.AVAILABLE).distinct()

    def unavailable_only(self):
        """Keep books that have copies but none of them are on the shelf."""
        return self.exclude(copies__status=BookCopy.Status.AVAILABLE).distinct()


class Book(TimestampedModel):
    """Bibliographic record. Physical units live in the related ``BookCopy`` rows."""

    title = models.CharField(max_length=240, db_index=True)
    slug = models.SlugField(max_length=260, unique=True, blank=True)
    subtitle = models.CharField(max_length=240, blank=True)
    isbn = models.CharField(max_length=20, unique=True, null=True, blank=True)
    authors = models.ManyToManyField(Author, related_name="books", blank=True)
    categories = models.ManyToManyField(Category, related_name="books", blank=True)
    subject = models.ForeignKey(
        Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="books")
    publisher = models.CharField(max_length=160, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    edition = models.CharField(max_length=40, blank=True)
    language = models.CharField(max_length=40, default="English")
    page_count = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    cover = models.ImageField(upload_to="covers/", blank=True, null=True)
    featured = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)

    objects = BookQuerySet.as_manager()

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["is_active", "title"], name="book_active_title_idx"),
            models.Index(fields=["is_active", "featured"], name="book_active_featured_idx"),
            models.Index(fields=["subject", "publication_year"], name="book_subject_year_idx"),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.title)[:240] or "book"
        candidate, suffix = base, 2
        while Book.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def get_absolute_url(self):
        return reverse("core:book_detail", args=[self.slug])

    # -- Inventory ------------------------------------------------------
    # Counts are derived from the BookCopy rows so there is exactly one
    # source of truth and the numbers can never drift or go negative.

    @property
    def total_copies(self):
        cached = getattr(self, "_prefetched_objects_cache", None)
        if cached and "copies" in cached:
            return len(cached["copies"])
        return self.copies.count()

    @property
    def available_copies(self):
        cached = getattr(self, "_prefetched_objects_cache", None)
        if cached and "copies" in cached:
            return sum(1 for copy in cached["copies"]
                       if copy.status == BookCopy.Status.AVAILABLE)
        return self.copies.filter(status=BookCopy.Status.AVAILABLE).count()

    @property
    def is_available(self):
        return self.is_active and self.available_copies > 0

    @property
    def author_names(self):
        names = [author.name for author in self.authors.all()]
        return ", ".join(names) if names else "LibTrack Collection"

    @property
    def category_names(self):
        return [category.name for category in self.categories.all()]

    @property
    def cover_variant(self):
        """Pick one of the four designed cover artworks, stable per book.

        The stylesheet ships four editorial cover treatments. Hashing the slug
        keeps a book on the same artwork across every page without storing a
        column that only affects presentation.
        """
        variants = getattr(settings, "LIBRARY_COVER_VARIANTS",
                           ("architecture", "topography", "grid", "orbital"))
        return variants[sum(ord(ch) for ch in (self.slug or self.title)) % len(variants)]


class BookCopy(TimestampedModel):
    """One physical copy of a book - the unit that is actually loaned out."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ON_LOAN = "on_loan", "On loan"
        RESERVED = "reserved", "Reserved"
        REPAIR = "repair", "In repair"
        LOST = "lost", "Lost"

    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="copies")
    accession_number = models.CharField(max_length=40, unique=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    shelf_location = models.CharField(max_length=80, blank=True)
    acquired_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["accession_number"]
        indexes = [
            models.Index(fields=["book", "status"], name="copy_book_status_idx"),
        ]

    def __str__(self):
        return f"{self.accession_number} — {self.book.title}"


class DigitalMaterial(TimestampedModel):
    """A downloadable or externally linked learning resource."""

    class MaterialType(models.TextChoices):
        EBOOK = "ebook", "E-book"
        PAPER = "paper", "Research paper"
        NOTES = "notes", "Study notes"
        JOURNAL = "journal", "Journal"
        OTHER = "other", "Other"

    title = models.CharField(max_length=240, db_index=True)
    material_type = models.CharField(
        max_length=12, choices=MaterialType.choices, default=MaterialType.OTHER)
    book = models.ForeignKey(
        Book, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="digital_materials", help_text="Optional link back to a catalogue title.")
    subject = models.ForeignKey(
        Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="materials")
    categories = models.ManyToManyField(Category, related_name="materials", blank=True)
    authors = models.ManyToManyField(Author, related_name="digital_materials", blank=True)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to="materials/", blank=True)
    external_url = models.URLField(max_length=500, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    # Only public materials are offered to students on the catalogue pages.
    is_public = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["material_type", "is_public"], name="material_type_public_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(file="") | ~models.Q(external_url=""),
                name="material_has_a_source"),
        ]

    def __str__(self):
        return self.title

    @property
    def has_access(self):
        return bool(self.file or self.external_url)

    @property
    def author_names(self):
        names = [author.name for author in self.authors.all()]
        return ", ".join(names)


class Loan(TimestampedModel):
    """A borrowing record - the project's ``BorrowRecord`` table.

    One row tracks a single borrowing event from request through to return, so
    the complete history survives later catalogue edits.
    """

    class Status(models.TextChoices):
        REQUESTED = "requested", "Requested"
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"
        OVERDUE = "overdue", "Overdue"
        REJECTED = "rejected", "Rejected"

    #: Statuses that keep a copy out of the library.
    ACTIVE_STATUSES = (Status.REQUESTED, Status.ISSUED, Status.OVERDUE)
    #: Statuses that mean the student is still holding the book.
    ON_LOAN_STATUSES = (Status.ISSUED, Status.OVERDUE)
    #: Statuses that are finished and will never change again.
    CLOSED_STATUSES = (Status.RETURNED, Status.REJECTED)

    student = models.ForeignKey(
        StudentProfile, on_delete=models.PROTECT, related_name="loans")
    book = models.ForeignKey(Book, on_delete=models.PROTECT, related_name="loans")
    # Null while a request is still waiting for a librarian decision.
    copy = models.ForeignKey(
        BookCopy, null=True, blank=True, on_delete=models.PROTECT, related_name="loans")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    renewal_count = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(5)])
    fine_amount = models.DecimalField(
        max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loans_issued")
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loans_received")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["student", "status"], name="loan_student_status_idx"),
            models.Index(fields=["status", "due_at"], name="loan_status_due_idx"),
            models.Index(fields=["book", "status"], name="loan_book_status_idx"),
            models.Index(fields=["created_at"], name="loan_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(fine_amount__gte=0), name="loan_fine_nonnegative"),
            models.CheckConstraint(
                condition=models.Q(issued_at__isnull=True, due_at__isnull=True)
                | models.Q(due_at__gte=models.F("issued_at")),
                name="loan_due_after_issue"),
            models.CheckConstraint(
                condition=models.Q(returned_at__isnull=True)
                | models.Q(issued_at__isnull=True)
                | models.Q(returned_at__gte=models.F("issued_at")),
                name="loan_return_after_issue"),
        ]

    def __str__(self):
        return f"{self.student.student_id} — {self.book.title} ({self.get_status_display()})"

    @property
    def is_overdue(self):
        """Overdue is derived from the due date, never stored as a guess."""
        if self.status not in self.ON_LOAN_STATUSES or not self.due_at:
            return False
        from django.utils import timezone
        return self.due_at < timezone.now()

    @property
    def days_until_due(self):
        from django.utils import timezone
        if not self.due_at or self.returned_at:
            return None
        return (self.due_at.date() - timezone.localdate()).days

    @property
    def can_renew(self):
        """Renewal is allowed once, and never while the book is overdue."""
        from django.conf import settings
        if self.status != self.Status.ISSUED or self.is_overdue:
            return False
        return self.renewal_count < settings.LIBRARY_RULES["MAX_RENEWALS"]


class ReadingList(TimestampedModel):
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="reading_lists")
    name = models.CharField(max_length=100, default="My reading list")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["student", "name"], name="reading_list_student_name_uniq"),
        ]

    def __str__(self):
        return f"{self.student.student_id} — {self.name}"


class SavedResource(TimestampedModel):
    """A book or material a student bookmarked, always via a reading list."""

    reading_list = models.ForeignKey(
        ReadingList, on_delete=models.CASCADE, related_name="resources")
    book = models.ForeignKey(
        Book, null=True, blank=True, on_delete=models.CASCADE, related_name="saved_in_lists")
    material = models.ForeignKey(
        DigitalMaterial, null=True, blank=True, on_delete=models.CASCADE,
        related_name="saved_in_lists")
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(book__isnull=False, material__isnull=True)
                           | models.Q(book__isnull=True, material__isnull=False)),
                name="saved_resource_one_target"),
        ]

    def __str__(self):
        return f"{self.reading_list}: {self.book or self.material}"


class Review(TimestampedModel):
    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="reviews")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "book"], name="review_student_book_uniq"),
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]
        indexes = [
            models.Index(fields=["book", "is_published", "created_at"], name="review_book_pub_date_idx"),
        ]

    def __str__(self):
        return f"{self.rating}/5 — {self.book.title} by {self.student.student_id}"


class ActivityLog(models.Model):
    """Audit trail. Every circulation and staff action writes one row here."""

    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        SEARCH = "search", "Search"
        BORROW = "borrow", "Borrowed book"
        REQUEST = "request", "Requested book"
        RETURN = "return", "Returned book"
        RENEW = "renew", "Renewed book"
        REJECT = "reject", "Rejected request"
        SAVE = "save", "Saved resource"
        REVIEW = "review", "Reviewed book"
        ADMIN = "admin", "Administrative action"
        OTHER = "other", "Other"

    student = models.ForeignKey(
        StudentProfile, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activities")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="activity_logs")
    action = models.CharField(max_length=12, choices=Action.choices, db_index=True)
    description = models.CharField(max_length=240, blank=True)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["student", "occurred_at"], name="activity_student_date_idx"),
            models.Index(fields=["action", "occurred_at"], name="activity_action_date_idx"),
        ]

    def __str__(self):
        return (f"{self.get_action_display()} — {self.actor_name} "
                f"— {self.occurred_at:%Y-%m-%d %H:%M}")

    @property
    def actor_name(self):
        """Who caused this event, safe to render for any combination of fields."""
        if self.student_id:
            return self.student.display_name
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return "System"

    @property
    def actor_initials(self):
        source = self.actor_name
        return source[:2].upper() if source else "LT"
