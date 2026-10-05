"""Django admin registrations.

The custom admin site is the back-office escape hatch; the product pages in
``core.views`` remain the primary librarian interface.
"""

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
    Review,
    SavedResource,
    StudentProfile,
    Subject,
)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ("student_id", "user", "department", "semester", "enrollment_year", "is_active")
    list_filter = ("is_active", "department", "semester", "user__is_active")
    search_fields = ("student_id", "user__username", "user__first_name",
                     "user__last_name", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(Author)
class AuthorAdmin(admin.ModelAdmin):
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "book_count")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}

    @admin.display(description="Titles")
    def book_count(self, obj):
        return obj.books.count()


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ("name", "code")
    search_fields = ("name", "code")


class BookCopyInline(admin.TabularInline):
    model = BookCopy
    extra = 0
    fields = ("accession_number", "status", "shelf_location", "acquired_on")


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("title", "isbn", "subject", "publication_year",
                    "is_active", "featured", "copy_count", "available_count")
    list_filter = ("is_active", "featured", "subject", "categories", "publication_year")
    search_fields = ("title", "subtitle", "isbn", "authors__name", "publisher")
    filter_horizontal = ("authors", "categories")
    inlines = (BookCopyInline,)
    readonly_fields = ("slug", "created_at", "updated_at")

    @admin.display(description="Copies")
    def copy_count(self, obj):
        return obj.total_copies

    @admin.display(description="Available")
    def available_count(self, obj):
        return obj.available_copies


@admin.register(BookCopy)
class BookCopyAdmin(admin.ModelAdmin):
    list_display = ("accession_number", "book", "status", "shelf_location", "acquired_on")
    list_filter = ("status", "shelf_location")
    search_fields = ("accession_number", "book__title", "book__isbn")
    autocomplete_fields = ("book",)


@admin.register(DigitalMaterial)
class DigitalMaterialAdmin(admin.ModelAdmin):
    list_display = ("title", "material_type", "book", "subject", "is_public", "publication_date")
    list_filter = ("material_type", "is_public", "subject", "categories")
    search_fields = ("title", "authors__name", "description")
    filter_horizontal = ("authors", "categories")
    autocomplete_fields = ("book",)


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("student", "book", "copy", "status", "issued_at",
                    "due_at", "returned_at", "renewal_count")
    list_filter = ("status", "created_at", "due_at")
    search_fields = ("student__student_id", "student__user__username",
                     "book__title", "copy__accession_number")
    autocomplete_fields = ("student", "book", "copy", "issued_by", "received_by")
    date_hierarchy = "created_at"
    readonly_fields = ("requested_at",)


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
    search_fields = ("description", "student__student_id", "user__username",
                     "object_type", "object_id")
    readonly_fields = tuple(field.name for field in ActivityLog._meta.fields)
    date_hierarchy = "occurred_at"
