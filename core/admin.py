from django.contrib import admin

from .models import (
    ActivityLog,
    Author,
    Book,
    BookCopy,
    Category,
    DigitalMaterial,
    Loan,
    ReadingList,
    Reservation,
    Review,
    SavedResource,
    StudentProfile,
    Subject,
)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "department", "semester", "enrollment_year")
    list_filter = ("department", "semester", "enrollment_year")
    search_fields = ("student_id", "user__username", "user__first_name", "user__last_name", "user__email")


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 0


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "isbn", "subject", "publication_year", "is_active", "copy_count")
    list_filter = ("is_active", "subject", "categories", "publication_year")
    search_fields = ("title", "subtitle", "isbn", "authors__name", "publisher")
    filter_horizontal = ("authors", "categories")
    inlines = (BookCopyInline,)

    @admin.display(description="Copies")
    def copy_count(self, obj):
        return obj.copies.count()


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ("accession_number", "book", "status", "shelf_location", "acquired_on")
    list_filter = ("status", "shelf_location")
    search_fields = ("accession_number", "book__title", "book__isbn")
    autocomplete_fields = ("book",)


@admin.register(DigitalMaterial)
class DigitalMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "material_type", "subject", "is_active", "publication_date")
    list_filter = ("material_type", "is_active", "subject", "categories")
    search_fields = ("title", "authors__name", "description")
    filter_horizontal = ("authors", "categories")


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("student", "copy", "issued_at", "due_at", "returned_at", "status", "fine_amount")
    list_filter = ("status", "issued_at", "due_at")
    search_fields = ("student__student_id", "student__user__username", "copy__accession_number", "copy__book__title")
    autocomplete_fields = ("student", "copy", "issued_by", "received_by")
    date_hierarchy = "issued_at"


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("student", "book", "status", "queued_at", "ready_until", "fulfilled_at")
    list_filter = ("status", "queued_at")
    search_fields = ("student__student_id", "book__title", "book__isbn")
    autocomplete_fields = ("student", "book")


@admin.register(ReadingList)
class ReadingListAdmin(admin.ModelAdmin):
    list_display = ("name", "student", "is_default", "created_at")
    list_filter = ("is_default", "created_at")
    search_fields = ("name", "student__student_id", "student__user__username")
    autocomplete_fields = ("student",)


@admin.register(SavedResource)
class SavedResourceAdmin(admin.ModelAdmin):
    list_display = ("reading_list", "book", "material", "created_at")
    search_fields = ("reading_list__student__student_id", "book__title", "material__title")
    autocomplete_fields = ("reading_list", "book", "material")


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("book", "student", "rating", "is_published", "created_at")
    list_filter = ("rating", "is_published", "created_at")
    search_fields = ("book__title", "student__student_id", "title", "body")
    autocomplete_fields = ("book", "student")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "action", "student", "user", "description")
    list_filter = ("action", "occurred_at")
    search_fields = ("description", "student__student_id", "user__username", "object_type", "object_id")
    readonly_fields = tuple(field.name for field in ActivityLog._meta.fields)
    date_hierarchy = "occurred_at"
