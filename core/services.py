"""Circulation services and report queries.

Every function that changes stock runs inside a database transaction and locks
the rows it touches with ``select_for_update()``. That is what stops two
simultaneous requests from lending the same physical copy.

Business limits are read from ``settings.LIBRARY_RULES`` so the numbers are
configurable rather than scattered through the code.
"""

from datetime import timedelta
from decimal import Decimal
import calendar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import (ActivityLog, Author, Book, BookCopy, Category, DigitalMaterial,
                     Loan, ReadingList, Review, SavedResource, StudentProfile)

DAILY_OVERDUE_FINE = Decimal("10.00")


def rules():
    """Shortcut to the configured circulation limits."""
    return settings.LIBRARY_RULES


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def log_action(action, *, student=None, user=None, description="", obj=None, metadata=None):
    """Write one audit row. Never raises into the caller's transaction."""
    try:
        ActivityLog.objects.create(
            action=action, student=student, user=user,
            description=description[:240],
            object_type=obj.__class__.__name__ if obj else "",
            object_id=str(obj.pk) if obj else "",
            metadata=metadata or {},
        )
    except Exception:  # pragma: no cover - auditing must not break circulation
        pass


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------

def available_copies_qs(book):
    return book.copies.filter(status=BookCopy.Status.AVAILABLE)


def sync_overdue_statuses(loans=None):
    """Flip issued loans to OVERDUE once their due date has passed.

    Overdue is a derived state, so it is recalculated rather than trusted from
    a stale column.
    """
    now = timezone.now()
    queryset = Loan.objects.filter(status=Loan.Status.ISSUED, due_at__lt=now)
    if loans is not None:
        queryset = queryset.filter(pk__in=[loan.pk for loan in loans])
    updated = queryset.update(status=Loan.Status.OVERDUE)
    if loans is not None:
        for loan in loans:
            if loan.status == Loan.Status.ISSUED and loan.due_at and loan.due_at < now:
                loan.status = Loan.Status.OVERDUE
    return updated


def active_loan_count(student):
    return Loan.objects.filter(
        student=student, status__in=Loan.ON_LOAN_STATUSES).count()


def _next_accession_number(book):
    """Build a unique accession number for a new physical copy."""
    base = (book.isbn or f"LIB{book.pk:05d}")[-8:].upper().replace("-", "")
    existing = BookCopy.objects.filter(book=book).count() + 1
    while BookCopy.objects.filter(accession_number=f"{base}-{existing:03d}").exists():
        existing += 1
    return f"{base}-{existing:03d}"


def add_copies(book, count, *, shelf_location=""):
    """Create ``count`` physical copies for a book. Returns the new rows."""
    if count < 0:
        raise ValidationError("Copy count cannot be negative.")
    created = []
    for _ in range(count):
        copy = BookCopy.objects.create(
            book=book,
            accession_number=_next_accession_number(book),
            status=BookCopy.Status.AVAILABLE,
            shelf_location=shelf_location,
        )
        created.append(copy)
    return created


# ---------------------------------------------------------------------------
# Borrowing
# ---------------------------------------------------------------------------

def _resolve_student(student):
    if isinstance(student, StudentProfile):
        return student
    return StudentProfile.objects.select_related("user").get(pk=student)


def _ensure_borrowable(student):
    """Reject accounts that are not allowed to borrow."""
    if not student.is_active:
        raise ValidationError("Your library account has been deactivated. Please contact the librarian.")
    if not student.user.is_active:
        raise ValidationError("Your login has been disabled. Please contact the librarian.")


def _guard_loan_limits(student, book, now):
    """Apply the loan limit and the one-active-loan-per-title rule."""
    sync_overdue_statuses()
    limit = rules()["MAX_ACTIVE_LOANS"]
    active = list(Loan.objects.select_for_update().filter(
        student=student, status__in=Loan.ON_LOAN_STATUSES))
    if len(active) >= limit:
        raise ValidationError(
            f"You already have {limit} books on loan. Return a book before borrowing another.")
    if any(loan.book_id == book.pk for loan in active):
        raise ValidationError(f"You already have “{book.title}” on loan.")


@transaction.atomic
def request_book(student, book, *, requested_at=None):
    """Queue a request for a title. Used when no copy is free right now.

    No inventory moves here: a librarian approves the request later.
    """
    student = _resolve_student(student)
    _ensure_borrowable(student)
    book = Book.objects.select_for_update().get(pk=book.pk)
    if not book.is_active:
        raise ValidationError("This title is not available for lending.")

    now = requested_at or timezone.now()
    _guard_loan_limits(student, book, now)
    # A second request for the same title would be noise on the librarian's desk.
    if Loan.objects.filter(student=student, book=book,
                           status=Loan.Status.REQUESTED).exists():
        raise ValidationError(f"You already have a pending request for “{book.title}”.")
    loan = Loan.objects.create(
        student=student, book=book, status=Loan.Status.REQUESTED, requested_at=now)
    log_action(ActivityLog.Action.REQUEST, student=student,
               description=f"Requested {book.title}", obj=loan)
    return loan


@transaction.atomic
def borrow_book(student, book, *, due_at=None, issued_by=None, notes="", actor=None):
    """Lend one available copy to a student.

    Locks the book and copy rows, re-checks every rule, creates the loan and
    marks the copy on loan - all in one transaction.
    """
    student = _resolve_student(student)
    _ensure_borrowable(student)
    book = Book.objects.select_for_update().get(pk=book.pk)
    if not book.is_active:
        raise ValidationError("This title is not available for lending.")

    now = timezone.now()
    _guard_loan_limits(student, book, now)

    copy = (BookCopy.objects.select_for_update()
            .select_related("book")
            .filter(book=book, status=BookCopy.Status.AVAILABLE)
            .order_by("accession_number")
            .first())
    if copy is None:
        raise ValidationError("No copies of this title are available right now.")

    due_at = due_at or now + timedelta(days=rules()["LOAN_DAYS"])
    if timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at, timezone.get_current_timezone())
    if due_at <= now:
        raise ValidationError("The due date must be after the issue date.")

    loan = Loan.objects.create(
        student=student, book=book, copy=copy, status=Loan.Status.ISSUED,
        issued_at=now, due_at=due_at, issued_by=issued_by, notes=notes)
    copy.status = BookCopy.Status.ON_LOAN
    copy.save(update_fields=["status", "updated_at"])

    # A request for the same title is satisfied by this issue.
    Loan.objects.filter(student=student, book=book, status=Loan.Status.REQUESTED).update(
        status=Loan.Status.REJECTED, notes="Fulfilled by a direct issue.")

    log_action(ActivityLog.Action.BORROW, student=student, user=issued_by or actor,
               description=f"Borrowed {book.title}", obj=loan,
               metadata={"accession_number": copy.accession_number})
    return loan


@transaction.atomic
def approve_request(loan, *, issued_by=None, due_at=None, actor=None):
    """Turn a pending request into a real loan by assigning a free copy."""
    loan = (Loan.objects.select_for_update()
            .select_related("student__user", "book")
            .get(pk=_pk(loan)))
    if loan.status != Loan.Status.REQUESTED:
        raise ValidationError("That request is no longer pending.")
    _ensure_borrowable(loan.student)
    book = Book.objects.select_for_update().get(pk=loan.book_id)
    if not book.is_active:
        raise ValidationError("This title is no longer available for lending.")

    now = timezone.now()
    sync_overdue_statuses()
    limit = rules()["MAX_ACTIVE_LOANS"]
    active = list(Loan.objects.select_for_update().filter(
        student=loan.student, status__in=Loan.ON_LOAN_STATUSES))
    if len(active) >= limit:
        raise ValidationError(
            f"{loan.student.display_name} already holds {limit} books and cannot take another.")

    copy = (BookCopy.objects.select_for_update()
            .filter(book=book, status=BookCopy.Status.AVAILABLE)
            .order_by("accession_number")
            .first())
    if copy is None:
        raise ValidationError("No copies of this title are free yet. The request stays pending.")

    loan.status = Loan.Status.ISSUED
    loan.copy = copy
    loan.issued_at = now
    loan.due_at = due_at or now + timedelta(days=rules()["LOAN_DAYS"])
    loan.issued_by = issued_by
    loan.save(update_fields=["status", "copy", "issued_at", "due_at", "issued_by", "updated_at"])
    copy.status = BookCopy.Status.ON_LOAN
    copy.save(update_fields=["status", "updated_at"])

    log_action(ActivityLog.Action.BORROW, student=loan.student, user=issued_by or actor,
               description=f"Approved request for {book.title}", obj=loan)
    return loan


@transaction.atomic
def reject_request(loan, *, reason="", actor=None):
    """Close a pending request without lending anything."""
    loan = Loan.objects.select_for_update().get(pk=_pk(loan))
    if loan.status != Loan.Status.REQUESTED:
        raise ValidationError("That request is no longer pending.")
    loan.status = Loan.Status.REJECTED
    loan.notes = reason[:2000]
    loan.save(update_fields=["status", "notes", "updated_at"])
    log_action(ActivityLog.Action.REJECT, student=loan.student, user=actor,
               description=f"Rejected request for {loan.book.title}", obj=loan)
    return loan


def renew_loan(loan, *, actor=None):
    """Extend a loan by the configured renewal period, once.

    The overdue refresh runs before the transaction opens: it is derived state,
    and it has to survive even though a rejected renewal rolls its own
    transaction back.
    """
    loan_id = _pk(loan)
    sync_overdue_statuses()

    with transaction.atomic():
        loan = (Loan.objects.select_for_update()
                .select_related("book", "student__user")
                .get(pk=loan_id))
        if loan.status != Loan.Status.ISSUED:
            if loan.status == Loan.Status.OVERDUE:
                raise ValidationError(
                    "An overdue book must be returned before it can be renewed.")
            raise ValidationError("Only books that are currently on loan can be renewed.")
        limit = rules()["MAX_RENEWALS"]
        if loan.renewal_count >= limit:
            raise ValidationError(
                f"This book has already been renewed {limit} time(s) and cannot be extended again.")

        loan.renewal_count += 1
        base = loan.due_at if loan.due_at and loan.due_at > timezone.now() else timezone.now()
        loan.due_at = base + timedelta(days=rules()["RENEWAL_DAYS"])
        loan.save(update_fields=["renewal_count", "due_at", "updated_at"])
        log_action(ActivityLog.Action.RENEW, student=loan.student, user=actor,
                   description=f"Renewed {loan.book.title}", obj=loan,
                   metadata={"due_at": loan.due_at.isoformat()})
    return loan


@transaction.atomic
def return_book(loan, *, received_by=None, returned_at=None, notes="", actor=None):
    """Close a loan and put the copy back on the shelf exactly once."""
    loan = (Loan.objects.select_for_update()
            .select_related("student__user", "book", "copy")
            .get(pk=_pk(loan)))
    if loan.status in Loan.CLOSED_STATUSES or loan.returned_at:
        raise ValidationError("This loan has already been closed.")

    now = returned_at or timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())
    if loan.issued_at and now < loan.issued_at:
        raise ValidationError("The return date cannot be earlier than the issue date.")

    overdue_days = 0
    if loan.due_at and now > loan.due_at:
        overdue_days = (now.date() - loan.due_at.date()).days

    loan.status = Loan.Status.RETURNED
    loan.returned_at = now
    loan.received_by = received_by
    loan.fine_amount = DAILY_OVERDUE_FINE * max(0, overdue_days)
    if notes:
        loan.notes = (loan.notes + "\n" + notes).strip()[:2000]
    loan.save(update_fields=["status", "returned_at", "received_by", "fine_amount",
                             "notes", "updated_at"])

    if loan.copy_id:
        copy = BookCopy.objects.select_for_update().get(pk=loan.copy_id)
        if copy.status == BookCopy.Status.ON_LOAN:
            copy.status = BookCopy.Status.AVAILABLE
            copy.save(update_fields=["status", "updated_at"])

    log_action(ActivityLog.Action.RETURN, student=loan.student, user=received_by or actor,
               description=f"Returned {loan.book.title}", obj=loan,
               metadata={"overdue_days": max(0, overdue_days)})
    return loan


def _pk(value):
    return value.pk if hasattr(value, "pk") else value


# ---------------------------------------------------------------------------
# Reading lists
# ---------------------------------------------------------------------------

def toggle_saved(student, book):
    """Add a book to the default reading list, or remove it if already saved."""
    reading_list, _ = ReadingList.objects.get_or_create(
        student=student, is_default=True, defaults={"name": "My reading list"})
    saved, created = SavedResource.objects.get_or_create(
        reading_list=reading_list, book=book)
    if created:
        log_action(ActivityLog.Action.SAVE, student=student,
                   description=f"Saved {book.title}", obj=book)
    else:
        saved.delete()
    return created


# ---------------------------------------------------------------------------
# Dashboards and reports - all values come from aggregate queries
# ---------------------------------------------------------------------------

def student_dashboard_data(student, *, now=None):
    """Counters, loans and history for one student."""
    now = now or timezone.now()
    sync_overdue_statuses()
    loans = Loan.objects.filter(student=student).select_related("book", "copy")
    on_loan = loans.filter(status__in=Loan.ON_LOAN_STATUSES)
    due_soon_days = rules()["DUE_SOON_DAYS"]
    return {
        "active_loans": on_loan.count(),
        "overdue_loans": on_loan.filter(due_at__lt=now).count(),
        "returned_loans": loans.filter(status=Loan.Status.RETURNED).count(),
        "pending_requests": loans.filter(status=Loan.Status.REQUESTED).count(),
        "due_soon": on_loan.filter(
            due_at__gte=now,
            due_at__lte=now + timedelta(days=due_soon_days)).count(),
        "saved_resources": SavedResource.objects.filter(
            reading_list__student=student).count(),
        "active_loan_list": on_loan.order_by("due_at"),
        "upcoming_due": on_loan.filter(due_at__gte=now).order_by("due_at")[:5],
        "recent_loans": loans.order_by("-created_at")[:6],
        "recently_added": Book.objects.active().with_availability().order_by("-created_at")[:6],
        "recent_activity": ActivityLog.objects.filter(student=student).order_by("-occurred_at")[:8],
        "review_average": Review.objects.filter(student=student).aggregate(
            value=Avg("rating"))["value"],
    }


def librarian_dashboard_data():
    """Headline counters and recent activity for the staff overview."""
    now = timezone.now()
    sync_overdue_statuses()
    active_loans = Loan.objects.filter(status__in=Loan.ON_LOAN_STATUSES)
    return {
        "total_books": Book.objects.active().count(),
        "total_copies": BookCopy.objects.filter(book__is_active=True).count(),
        "available_copies": BookCopy.objects.filter(
            book__is_active=True, status=BookCopy.Status.AVAILABLE).count(),
        "student_count": StudentProfile.objects.count(),
        "active_students": StudentProfile.objects.filter(
            is_active=True, user__is_active=True).count(),
        "current_loans": active_loans.count(),
        "overdue_count": active_loans.filter(due_at__lt=now).count(),
        "pending_requests": Loan.objects.filter(status=Loan.Status.REQUESTED).count(),
        "digital_materials": DigitalMaterial.objects.filter(is_public=True).count(),
        "recent_activity": ActivityLog.objects.select_related(
            "student__user", "user").order_by("-occurred_at")[:8],
        "recent_loans": Loan.objects.select_related(
            "student__user", "book").order_by("-created_at")[:8],
        "monthly_circulation": monthly_circulation(now),
    }


def monthly_circulation(now=None, months=6):
    """Count books issued in each of the last ``months`` calendar months.

    Used by the librarian dashboard chart. The month list is built in Python
    so empty months still render as a zero bar rather than disappearing.
    """
    from django.db.models.functions import ExtractMonth, ExtractYear

    now = now or timezone.now()
    first = (now.replace(day=1) - timedelta(days=31 * (months - 1))).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0)

    rows = (Loan.objects.filter(created_at__gte=first)
            .annotate(year=ExtractYear("created_at"), month=ExtractMonth("created_at"))
            .values("year", "month")
            .annotate(total=Count("id")))

    counts = {(row["year"], row["month"]): row["total"] for row in rows}
    series = []
    year, month = first.year, first.month
    for _ in range(months):
        series.append({
            "label": f"{calendar.month_abbr[month].upper()}",
            "year": year,
            "total": counts.get((year, month), 0),
        })
        month += 1
        if month > 12:
            month, year = 1, year + 1
    peak = max((row["total"] for row in series), default=0)
    for row in series:
        # Height as a percentage of the busiest month, with a floor so a quiet
        # month is still visible as a thin bar.
        row["height"] = round(row["total"] / peak * 100) if peak else 4
    return series


def librarian_report_data(start=None, end=None):
    """Aggregated figures behind the librarian reports page."""
    now = timezone.now()
    start = start or now - timedelta(days=30)
    end = end or now
    sync_overdue_statuses()
    active_loans = Loan.objects.filter(status__in=Loan.ON_LOAN_STATUSES)
    period_loans = Loan.objects.filter(created_at__gte=start, created_at__lte=end)
    returned = Loan.objects.filter(returned_at__gte=start, returned_at__lte=end)
    return {
        "start": start,
        "end": end,
        "total_books": Book.objects.active().count(),
        "total_copies": BookCopy.objects.filter(book__is_active=True).count(),
        "available_copies": BookCopy.objects.filter(
            book__is_active=True, status=BookCopy.Status.AVAILABLE).count(),
        "active_students": StudentProfile.objects.filter(
            is_active=True, user__is_active=True).count(),
        "current_loans": active_loans.count(),
        "overdue_loans": active_loans.filter(due_at__lt=now).count(),
        "issued_in_period": period_loans.filter(status=Loan.Status.ISSUED).count(),
        "returned_in_period": returned.count(),
        "fines_in_period": returned.aggregate(total=Sum("fine_amount"))["total"] or Decimal("0.00"),
        "top_borrowed": (Book.objects.filter(loans__created_at__gte=start)
                         .annotate(borrow_count=Count("loans", distinct=True))
                         .order_by("-borrow_count", "title")[:8]),
        "department_loans": (StudentProfile.objects.values("department")
                             .annotate(loan_count=Count("loans", filter=Q(
                                 loans__created_at__gte=start, loans__created_at__lte=end)))
                             .order_by("-loan_count")[:8]),
        "category_breakdown": (Category.objects.annotate(
            title_count=Count("books", filter=Q(books__is_active=True),
                              distinct=True)).order_by("-title_count")[:8]),
        "active_loans_qs": active_loans.select_related("student__user", "book").order_by("due_at"),
        "returned_loans_qs": returned.select_related("student__user", "book").order_by("-returned_at"),
        "overdue_loans_qs": active_loans.filter(due_at__lt=now).select_related(
            "student__user", "book").order_by("due_at"),
    }


def catalogue_facets():
    """Category and availability values used to build the filter controls."""
    return {
        "categories": Category.objects.annotate(
            book_count=Count("books", filter=Q(books__is_active=True), distinct=True)
        ).order_by("name"),
        "authors": Author.objects.order_by("name")[:100],
    }
