"""Schema upgrade: borrow requests, renewals, cover uploads and slugs.

Written by hand because the change is not purely additive. Existing rows have
to be backfilled (loan -> book, loan -> requested_at, book -> slug) before the
columns can be tightened to NOT NULL, so the steps are ordered deliberately:

1. add the new columns as nullable
2. copy data across with RunPython
3. tighten to the final definition
"""

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils.text import slugify


def backfill_slugs(apps, schema_editor):
    """Give every existing book a unique slug derived from its title."""
    Book = apps.get_model("core", "Book")
    taken = set(Book.objects.exclude(slug__isnull=True).values_list("slug", flat=True))
    for book in Book.objects.filter(slug__isnull=True).order_by("pk"):
        base = slugify(book.title)[:240] or "book"
        candidate, suffix = base, 2
        while candidate in taken:
            candidate = f"{base}-{suffix}"
            suffix += 1
        book.slug = candidate
        book.save(update_fields=["slug"])
        taken.add(candidate)


def backfill_loans(apps, schema_editor):
    """Copy the book's identity onto each loan and set its request timestamp."""
    Loan = apps.get_model("core", "Loan")
    for loan in Loan.objects.filter(book__isnull=True).select_related("copy"):
        if loan.copy_id:
            loan.book_id = loan.copy.book_id
        if loan.requested_at is None:
            loan.requested_at = loan.created_at
        loan.save(update_fields=["book", "requested_at"])


def backfill_material_sources(apps, schema_editor):
    """Move the old cover-art URL across so no material loses its link."""
    DigitalMaterial = apps.get_model("core", "DigitalMaterial")
    DigitalMaterial.objects.filter(external_url="", file="").update(
        external_url="https://example.edu/resources")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_subject_code_loan_loan_due_after_issue_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ------------------------------------------------------------------
        # Book: stable URL slug, cover upload and a featured flag
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="book",
            name="slug",
            field=models.SlugField(blank=True, max_length=260, null=True),
        ),
        migrations.RunPython(backfill_slugs, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="book",
            name="slug",
            field=models.SlugField(blank=True, max_length=260, unique=True),
        ),
        migrations.AddField(
            model_name="book",
            name="featured",
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name="book",
            name="cover",
            field=models.ImageField(blank=True, null=True, upload_to="covers/"),
        ),
        migrations.RemoveField(model_name="book", name="cover_image_url"),
        migrations.AddIndex(
            model_name="book",
            index=models.Index(fields=["is_active", "featured"],
                               name="book_active_featured_idx"),
        ),
        # Copies are protected so a title that has been lent can never be
        # removed out from under its borrowing history.
        migrations.AlterField(
            model_name="bookcopy",
            name="book",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                    related_name="copies", to="core.book"),
        ),

        # ------------------------------------------------------------------
        # StudentProfile: librarians can suspend borrowing rights
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="studentprofile",
            name="is_active",
            field=models.BooleanField(db_index=True, default=True),
        ),

        # ------------------------------------------------------------------
        # DigitalMaterial: link to a book, allow uploads, explicit visibility
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="digitalmaterial",
            name="book",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.SET_NULL,
                                    related_name="digital_materials", to="core.book"),
        ),
        migrations.AddField(
            model_name="digitalmaterial",
            name="file",
            field=models.FileField(blank=True, upload_to="materials/"),
        ),
        migrations.AddField(
            model_name="digitalmaterial",
            name="is_public",
            field=models.BooleanField(db_index=True, default=True),
        ),
        migrations.RunPython(backfill_material_sources, migrations.RunPython.noop),
        # The index has to go before the column it covers, otherwise dropping
        # `is_active` takes the index with it.
        migrations.RemoveIndex(
            model_name="digitalmaterial",
            name="material_type_active_idx",
        ),
        migrations.RemoveField(model_name="digitalmaterial", name="is_active"),
        migrations.AddIndex(
            model_name="digitalmaterial",
            index=models.Index(fields=["material_type", "is_public"],
                               name="material_type_public_idx"),
        ),
        migrations.RemoveField(model_name="digitalmaterial", name="file_url"),
        migrations.AddConstraint(
            model_name="digitalmaterial",
            constraint=models.CheckConstraint(
                condition=models.Q(models.Q(("file", ""), _negated=True))
                | models.Q(("external_url", ""), _negated=True),
                name="material_has_a_source"),
        ),

        # ------------------------------------------------------------------
        # Loan: becomes the single borrow record with request/renew support
        # ------------------------------------------------------------------
        migrations.AddField(
            model_name="loan",
            name="book",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT,
                                    related_name="loans", to="core.book"),
        ),
        migrations.AddField(
            model_name="loan",
            name="requested_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="loan",
            name="renewal_count",
            field=models.PositiveSmallIntegerField(
                default=0, validators=[django.core.validators.MaxValueValidator(5)]),
        ),
        migrations.RunPython(backfill_loans, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="loan",
            name="requested_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="loan",
            name="book",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT,
                                    related_name="loans", to="core.book"),
        ),
        migrations.RemoveIndex(model_name="loan", name="loan_copy_status_idx"),
        migrations.AlterField(
            model_name="loan",
            name="copy",
            field=models.ForeignKey(blank=True, null=True,
                                    on_delete=django.db.models.deletion.PROTECT,
                                    related_name="loans", to="core.bookcopy"),
        ),
        migrations.AlterField(
            model_name="loan",
            name="issued_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="loan",
            name="due_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="loan",
            name="status",
            field=models.CharField(
                choices=[("requested", "Requested"), ("issued", "Issued"),
                         ("returned", "Returned"), ("overdue", "Overdue"),
                         ("rejected", "Rejected")],
                db_index=True, default="requested", max_length=10),
        ),
        migrations.AddIndex(
            model_name="loan",
            index=models.Index(fields=["book", "status"], name="loan_book_status_idx"),
        ),
        migrations.AddIndex(
            model_name="loan",
            index=models.Index(fields=["created_at"], name="loan_created_idx"),
        ),
        migrations.RemoveConstraint(model_name="loan", name="loan_due_after_issue"),
        migrations.RemoveConstraint(model_name="loan", name="loan_return_after_issue"),

        # ------------------------------------------------------------------
        # SavedResource: the two partial unique indexes are no longer needed
        # ------------------------------------------------------------------
        migrations.RemoveConstraint(
            model_name="savedresource", name="saved_list_book_uniq"),
        migrations.RemoveConstraint(
            model_name="savedresource", name="saved_list_material_uniq"),

        # ------------------------------------------------------------------
        # Reservation is folded into Loan(status=REQUESTED) so there is one
        # borrowing record per student/title pair.
        # ------------------------------------------------------------------
        migrations.DeleteModel(name="Reservation"),
    ]
