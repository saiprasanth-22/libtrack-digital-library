from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class StudentProfile(TimestampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="student_profile")
    student_id = models.CharField(max_length=32, unique=True)
    department = models.CharField(max_length=100, blank=True)
    semester = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(12)])
    phone = models.CharField(max_length=24, blank=True)
    enrollment_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["student_id"]
        indexes = [models.Index(fields=["department", "semester"], name="student_dept_sem_idx")]
        constraints = [models.CheckConstraint(condition=models.Q(semester__isnull=True) | models.Q(semester__gte=1, semester__lte=12), name="student_semester_1_to_12")]

    def __str__(self):
        return f"{self.student_id} — {self.user.get_full_name() or self.user.get_username()}"


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


class Book(TimestampedModel):
    title = models.CharField(max_length=240, db_index=True)
    subtitle = models.CharField(max_length=240, blank=True)
    isbn = models.CharField(max_length=20, unique=True, null=True, blank=True)
    authors = models.ManyToManyField(Author, related_name="books", blank=True)
    categories = models.ManyToManyField(Category, related_name="books", blank=True)
    subject = models.ForeignKey(Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="books")
    publisher = models.CharField(max_length=160, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    edition = models.CharField(max_length=40, blank=True)
    language = models.CharField(max_length=40, default="English")
    page_count = models.PositiveIntegerField(null=True, blank=True)
    description = models.TextField(blank=True)
    cover_image_url = models.URLField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["title"]
        indexes = [
            models.Index(fields=["is_active", "title"], name="book_active_title_idx"),
            models.Index(fields=["subject", "publication_year"], name="book_subject_year_idx"),
        ]

    def __str__(self):
        return self.title


class BookCopy(TimestampedModel):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ON_LOAN = "on_loan", "On loan"
        RESERVED = "reserved", "Reserved"
        REPAIR = "repair", "In repair"
        LOST = "lost", "Lost"

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="copies")
    accession_number = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    shelf_location = models.CharField(max_length=80, blank=True)
    acquired_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["accession_number"]
        indexes = [models.Index(fields=["book", "status"], name="copy_book_status_idx")]

    def __str__(self):
        return f"{self.accession_number} — {self.book.title}"


class DigitalMaterial(TimestampedModel):
    class MaterialType(models.TextChoices):
        EBOOK = "ebook", "E-book"
        PAPER = "paper", "Research paper"
        NOTES = "notes", "Study notes"
        JOURNAL = "journal", "Journal"
        OTHER = "other", "Other"

    title = models.CharField(max_length=240, db_index=True)
    material_type = models.CharField(max_length=12, choices=MaterialType.choices, default=MaterialType.OTHER)
    subject = models.ForeignKey(Subject, null=True, blank=True, on_delete=models.SET_NULL, related_name="materials")
    categories = models.ManyToManyField(Category, related_name="materials", blank=True)
    authors = models.ManyToManyField(Author, related_name="digital_materials", blank=True)
    description = models.TextField(blank=True)
    file_url = models.URLField(max_length=500, blank=True)
    external_url = models.URLField(max_length=500, blank=True)
    publication_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["title"]
        indexes = [models.Index(fields=["material_type", "is_active"], name="material_type_active_idx")]

    def __str__(self):
        return self.title


class Loan(TimestampedModel):
    class Status(models.TextChoices):
        ISSUED = "issued", "Issued"
        RETURNED = "returned", "Returned"
        OVERDUE = "overdue", "Overdue"
        LOST = "lost", "Lost"

    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT, related_name="loans")
    copy = models.ForeignKey(BookCopy, on_delete=models.PROTECT, related_name="loans")
    issued_at = models.DateTimeField()
    due_at = models.DateTimeField(db_index=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ISSUED, db_index=True)
    fine_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="loans_issued")
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="loans_received")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["student", "status"], name="loan_student_status_idx"),
            models.Index(fields=["status", "due_at"], name="loan_status_due_idx"),
            models.Index(fields=["copy", "status"], name="loan_copy_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(fine_amount__gte=0), name="loan_fine_nonnegative"),
            models.CheckConstraint(condition=models.Q(due_at__gte=models.F("issued_at")), name="loan_due_after_issue"),
            models.CheckConstraint(condition=models.Q(returned_at__isnull=True) | models.Q(returned_at__gte=models.F("issued_at")), name="loan_return_after_issue"),
        ]

    def __str__(self):
        return f"{self.student.student_id} — {self.copy.accession_number} ({self.get_status_display()})"


class Reservation(TimestampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        READY = "ready", "Ready for pickup"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="reservations")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reservations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    queued_at = models.DateTimeField(auto_now_add=True)
    ready_until = models.DateTimeField(null=True, blank=True)
    fulfilled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["queued_at"]
        indexes = [
            models.Index(fields=["book", "status", "queued_at"], name="reservation_queue_idx"),
            models.Index(fields=["student", "status"], name="reservation_student_idx"),
        ]

    def __str__(self):
        return f"{self.student.student_id} — {self.book.title} ({self.get_status_display()})"


class ReadingList(TimestampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="reading_lists")
    name = models.CharField(max_length=100, default="My reading list")
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["student", "name"], name="reading_list_student_name_uniq")]

    def __str__(self):
        return f"{self.student.student_id} — {self.name}"


class SavedResource(TimestampedModel):
    reading_list = models.ForeignKey(ReadingList, on_delete=models.CASCADE, related_name="resources")
    book = models.ForeignKey(Book, null=True, blank=True, on_delete=models.CASCADE, related_name="saved_in_lists")
    material = models.ForeignKey(DigitalMaterial, null=True, blank=True, on_delete=models.CASCADE, related_name="saved_in_lists")
    note = models.CharField(max_length=240, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(condition=(models.Q(book__isnull=False, material__isnull=True) | models.Q(book__isnull=True, material__isnull=False)), name="saved_resource_one_target"),
            models.UniqueConstraint(fields=["reading_list", "book"], name="saved_list_book_uniq"),
            models.UniqueConstraint(fields=["reading_list", "material"], name="saved_list_material_uniq"),
        ]

    def __str__(self):
        target = self.book or self.material
        return f"{self.reading_list}: {target}"


class Review(TimestampedModel):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name="reviews")
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    title = models.CharField(max_length=160, blank=True)
    body = models.TextField(blank=True)
    is_published = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["student", "book"], name="review_student_book_uniq"),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name="review_rating_1_to_5"),
        ]
        indexes = [models.Index(fields=["book", "is_published", "created_at"], name="review_book_pub_date_idx")]

    def __str__(self):
        return f"{self.rating}/5 — {self.book.title} by {self.student.student_id}"


class ActivityLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        SEARCH = "search", "Search"
        BORROW = "borrow", "Borrowed book"
        RETURN = "return", "Returned book"
        RESERVE = "reserve", "Reserved book"
        SAVE = "save", "Saved resource"
        REVIEW = "review", "Reviewed book"
        ADMIN = "admin", "Administrative action"
        OTHER = "other", "Other"

    student = models.ForeignKey(StudentProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="activities")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="activity_logs")
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
        actor = self.student.student_id if self.student_id else (self.user.get_username() if self.user_id else "System")
        return f"{self.get_action_display()} — {actor} — {self.occurred_at:%Y-%m-%d %H:%M}"
