"""Transactional library operations and aggregate query helpers."""

from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from .models import (ActivityLog, Book, BookCopy, Loan, Reservation, Review,
                     SavedResource, StudentProfile)

MAX_ACTIVE_LOANS = 5
DAILY_OVERDUE_FINE = Decimal("10.00")
RESERVATION_PICKUP_HOURS = 48


def _log(action, *, student=None, user=None, description="", obj=None, metadata=None):
    ActivityLog.objects.create(
        action=action, student=student, user=user,
        description=description[:240],
        object_type=obj.__class__.__name__ if obj else "",
        object_id=str(obj.pk) if obj else "",
        metadata=metadata or {},
    )


def _refresh_loan_status(loan, now=None):
    now = now or timezone.now()
    if loan.status == Loan.Status.ISSUED and loan.due_at < now:
        loan.status = Loan.Status.OVERDUE
        loan.save(update_fields=["status", "updated_at"])
    return loan


@transaction.atomic
def issue_book(student, copy, *, due_at=None, issued_by=None, notes=""):
    """Issue a copy after locking it, so concurrent requests cannot double-loan."""
    if not isinstance(student, StudentProfile):
        try:
            student = StudentProfile.objects.select_related("user").get(pk=student)
        except StudentProfile.DoesNotExist as exc:
            raise ValidationError("Select a valid student account.") from exc
    copy_id = copy.pk if isinstance(copy, BookCopy) else copy
    try:
        copy = BookCopy.objects.select_for_update().select_related("book").get(pk=copy_id)
    except BookCopy.DoesNotExist as exc:
        raise ValidationError("This library copy no longer exists.") from exc
    now = timezone.now()
    if not copy.book.is_active:
        raise ValidationError("This book is not currently available for lending.")
    # Synchronize stale overdue statuses before enforcing the active-loan limit.
    active = list(Loan.objects.select_for_update().filter(
        student=student, status__in=(Loan.Status.ISSUED, Loan.Status.OVERDUE)
    ))
    for loan in active:
        _refresh_loan_status(loan, now)
    if len(active) >= MAX_ACTIVE_LOANS:
        raise ValidationError(f"A student may have at most {MAX_ACTIVE_LOANS} active loans.")
    if any(loan.status == Loan.Status.OVERDUE for loan in active):
        raise ValidationError("Return overdue books before borrowing another title.")

    reservation = Reservation.objects.select_for_update().filter(
        book=copy.book, status=Reservation.Status.READY, ready_until__gt=now
    ).order_by("queued_at").first()
    if copy.status == BookCopy.Status.RESERVED:
        if not reservation or reservation.student_id != student.pk:
            raise ValidationError("This copy is reserved for another student.")
    elif copy.status != BookCopy.Status.AVAILABLE:
        raise ValidationError("This copy is not available to borrow.")
    if reservation and reservation.student_id != student.pk:
        raise ValidationError("This title is being held for the next student in the reservation queue.")

    due_at = due_at or now + timedelta(days=14)
    if timezone.is_naive(due_at):
        due_at = timezone.make_aware(due_at, timezone.get_current_timezone())
    if due_at <= now:
        raise ValidationError("The due date must be in the future.")

    loan = Loan.objects.create(student=student, copy=copy, issued_at=now, due_at=due_at,
                               issued_by=issued_by, notes=notes)
    copy.status = BookCopy.Status.ON_LOAN
    copy.save(update_fields=["status", "updated_at"])
    if reservation:
        reservation.status = Reservation.Status.FULFILLED
        reservation.fulfilled_at = now
        reservation.save(update_fields=["status", "fulfilled_at", "updated_at"])
    _log(ActivityLog.Action.BORROW, student=student, user=issued_by,
         description=f"Borrowed {copy.book.title}", obj=loan)
    return loan


def _make_next_reservation_ready(book, now=None):
    now = now or timezone.now()
    # Expired holds are removed from the active queue before advancing it.
    Reservation.objects.filter(book=book, status=Reservation.Status.READY,
                               ready_until__lte=now).update(status=Reservation.Status.EXPIRED)
    next_reservation = Reservation.objects.select_for_update().filter(
        book=book, status=Reservation.Status.QUEUED
    ).order_by("queued_at", "pk").first()
    if next_reservation:
        next_reservation.status = Reservation.Status.READY
        next_reservation.ready_until = now + timedelta(hours=RESERVATION_PICKUP_HOURS)
        next_reservation.save(update_fields=["status", "ready_until", "updated_at"])
    return next_reservation


@transaction.atomic
def return_book(loan, *, received_by=None, returned_at=None, notes=""):
    """Return a loan once, compute its fine, and advance the reservation queue."""
    loan_id = loan.pk if isinstance(loan, Loan) else loan
    try:
        loan = Loan.objects.select_for_update().select_related("student__user", "copy__book").get(pk=loan_id)
    except Loan.DoesNotExist as exc:
        raise ValidationError("This loan record no longer exists.") from exc
    if loan.status in (Loan.Status.RETURNED, Loan.Status.LOST) or loan.returned_at:
        raise ValidationError("This loan has already been closed.")
    now = returned_at or timezone.now()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, timezone.get_current_timezone())
    if now < loan.issued_at:
        raise ValidationError("Return time cannot precede issue time.")

    loan.returned_at = now
    loan.received_by = received_by
    loan.status = Loan.Status.RETURNED
    overdue_days = max(0, (now.date() - loan.due_at.date()).days)
    loan.fine_amount = DAILY_OVERDUE_FINE * overdue_days
    if notes:
        loan.notes = (loan.notes + "\n" + notes).strip()[:2000]
    loan.save(update_fields=["returned_at", "received_by", "status", "fine_amount", "notes", "updated_at"])

    copy = BookCopy.objects.select_for_update().get(pk=loan.copy_id)
    next_hold = _make_next_reservation_ready(copy.book, now)
    copy.status = BookCopy.Status.RESERVED if next_hold else BookCopy.Status.AVAILABLE
    copy.save(update_fields=["status", "updated_at"])
    _log(ActivityLog.Action.RETURN, student=loan.student, user=received_by,
         description=f"Returned {copy.book.title}", obj=loan,
         metadata={"fine": str(loan.fine_amount), "overdue_days": overdue_days})
    return loan


@transaction.atomic
def reserve_book(student, book, *, queued_at=None):
    """Join a title's FIFO hold queue, preventing duplicate live reservations."""
    if not isinstance(student, StudentProfile):
        try:
            student = StudentProfile.objects.get(pk=student)
        except StudentProfile.DoesNotExist as exc:
            raise ValidationError("Select a valid student account.") from exc
    book_id = book.pk if isinstance(book, Book) else book
    try:
        book = Book.objects.select_for_update().get(pk=book_id, is_active=True)
    except Book.DoesNotExist as exc:
        raise ValidationError("This title is unavailable for reservation.") from exc
    existing = Reservation.objects.filter(student=student, book=book,
        status__in=(Reservation.Status.QUEUED, Reservation.Status.READY)).first()
    if existing:
        raise ValidationError("You already have an active reservation for this book.")
    if Loan.objects.filter(student=student, copy__book=book,
                           status__in=(Loan.Status.ISSUED, Loan.Status.OVERDUE)).exists():
        raise ValidationError("You already have this title on loan.")

    available_copy = BookCopy.objects.select_for_update().filter(
        book=book, status=BookCopy.Status.AVAILABLE
    ).order_by("accession_number").first()
    if available_copy and not Reservation.objects.filter(
        book=book, status__in=(Reservation.Status.QUEUED, Reservation.Status.READY)
    ).exists():
        raise ValidationError("A copy is available now; borrow it instead of reserving.")
    now = queued_at or timezone.now()
    reservation = Reservation.objects.create(student=student, book=book, queued_at=now)
    if available_copy:
        reservation.status = Reservation.Status.READY
        reservation.ready_until = now + timedelta(hours=RESERVATION_PICKUP_HOURS)
        reservation.save(update_fields=["status", "ready_until", "updated_at"])
        available_copy.status = BookCopy.Status.RESERVED
        available_copy.save(update_fields=["status", "updated_at"])
    _log(ActivityLog.Action.RESERVE, student=student,
         description=f"Reserved {book.title}", obj=reservation)
    return reservation


def student_dashboard_data(student):
    """Return database-backed counters and recent activity for one student."""
    now = timezone.now()
    loans = Loan.objects.filter(student=student).select_related("copy__book")
    active = loans.filter(status__in=(Loan.Status.ISSUED, Loan.Status.OVERDUE))
    return {
        "active_loans": active.count(),
        "due_soon": active.filter(due_at__gte=now, due_at__lte=now + timedelta(days=3)).count(),
        "overdue_loans": active.filter(due_at__lt=now).count(),
        "saved_resources": SavedResource.objects.filter(reading_list__student=student).count(),
        "reservations": Reservation.objects.filter(student=student,
            status__in=(Reservation.Status.QUEUED, Reservation.Status.READY)).count(),
        "recent_loans": loans.order_by("-issued_at")[:6],
        "upcoming_due": active.filter(due_at__gte=now).order_by("due_at")[:5],
        "recent_activity": ActivityLog.objects.filter(student=student).order_by("-occurred_at")[:8],
        "review_average": Review.objects.filter(student=student).aggregate(value=Avg("rating"))["value"],
    }


def librarian_report_data(start=None, end=None):
    """Aggregated report queries used by librarian dashboard and report export."""
    now = timezone.now()
    start = start or now - timedelta(days=30)
    end = end or now
    loans = Loan.objects.filter(issued_at__gte=start, issued_at__lte=end)
    active = Loan.objects.filter(status__in=(Loan.Status.ISSUED, Loan.Status.OVERDUE))
    return {
        "total_books": Book.objects.filter(is_active=True).count(),
        "total_copies": BookCopy.objects.filter(book__is_active=True).count(),
        "available_copies": BookCopy.objects.filter(book__is_active=True, status=BookCopy.Status.AVAILABLE).count(),
        "active_students": StudentProfile.objects.filter(user__is_active=True).count(),
        "current_loans": active.count(),
        "overdue_loans": active.filter(due_at__lt=now).count(),
        "issued_in_period": loans.count(),
        "returned_in_period": Loan.objects.filter(returned_at__gte=start, returned_at__lte=end).count(),
        "fines_in_period": Loan.objects.filter(returned_at__gte=start, returned_at__lte=end).aggregate(total=Sum("fine_amount"))["total"] or Decimal("0.00"),
        "top_borrowed": Book.objects.filter(copies__loans__issued_at__gte=start,
            copies__loans__issued_at__lte=end).annotate(borrow_count=Count("copies__loans", distinct=True))
            .order_by("-borrow_count", "title")[:8],
        "department_loans": StudentProfile.objects.values("department").annotate(
            loan_count=Count("loans", filter=Q(loans__issued_at__gte=start, loans__issued_at__lte=end))
        ).order_by("-loan_count")[:8],
        "recent_activity": ActivityLog.objects.select_related("student__user", "user").order_by("-occurred_at")[:12],
        "recent_loans": loans.select_related("student__user", "copy__book").order_by("-issued_at")[:12],
        "reviews_average": Review.objects.filter(is_published=True).aggregate(value=Avg("rating"))["value"],
    }
