from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

from .models import ActivityLog, Book, BookCopy, Loan, ReadingList, Reservation, SavedResource, StudentProfile


FALLBACK_BOOKS = [
    {"title": "Database System Concepts", "author": "A. Silberschatz", "kind": "Computer Science", "cover": "architecture", "progress": 72, "available": True, "slug": "database-system-concepts", "description": "A foundational guide to database design, implementation, and management.", "publisher": "McGraw Hill", "edition": "7th Edition", "isbn": "978-0-07-802215-9", "copies_available": 4, "copies_total": 7},
    {"title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "kind": "Data Systems", "cover": "topography", "progress": 46, "available": True, "slug": "designing-data-intensive-applications"},
    {"title": "The Pragmatic Programmer", "author": "Andrew Hunt", "kind": "Software Engineering", "cover": "grid", "progress": 31, "available": True, "slug": "the-pragmatic-programmer"},
    {"title": "Artificial Intelligence", "author": "Stuart Russell", "kind": "Machine Learning", "cover": "orbital", "progress": 58, "available": True, "slug": "artificial-intelligence"},
]


def _book_card(book):
    authors = list(book.authors.all()[:2])
    category = book.categories.first()
    cover = "architecture"
    text = f"{category.name if category else ''} {book.title}".lower()
    if any(term in text for term in ("data", "database", "distributed")):
        cover = "topography"
    elif any(term in text for term in ("program", "software", "code")):
        cover = "grid"
    elif any(term in text for term in ("intelligence", "machine", "ai")):
        cover = "orbital"
    copies = book.copies.all()
    available_count = copies.filter(status=BookCopy.Status.AVAILABLE).count()
    total_count = copies.count()
    return {
        "title": book.title,
        "author": ", ".join(a.name for a in authors) or "LibTrack Collection",
        "kind": category.name if category else (book.subject.name if book.subject_id else "Academic collection"),
        "cover": cover,
        "progress": 0,
        "available": available_count > 0,
        "slug": slugify(book.title),
        "record": book,
        "description": book.description,
        "publisher": book.publisher,
        "edition": book.edition,
        "isbn": book.isbn,
        "copies_available": available_count,
        "copies_total": total_count,
    }


def _catalogue():
    try:
        return [_book_card(book) for book in Book.objects.filter(is_active=True).prefetch_related("authors", "categories", "copies").select_related("subject")]
    except DatabaseError:
        # Allows the polished product preview to remain usable before migrations/seed data exist.
        return FALLBACK_BOOKS


def _book_by_slug(slug):
    try:
        for book in Book.objects.filter(is_active=True).prefetch_related("authors", "categories", "copies").select_related("subject"):
            if slugify(book.title) == slug:
                return _book_card(book)
    except DatabaseError:
        pass
    return next((book for book in FALLBACK_BOOKS if book["slug"] == slug), FALLBACK_BOOKS[0])


def _student_profile(user):
    profile, _ = StudentProfile.objects.get_or_create(
        user=user,
        defaults={"student_id": f"STU-{user.pk:06d}", "department": "Computer Science"},
    )
    return profile


def _log(user, action, description="", book=None):
    student = None
    if not user.is_staff:
        try:
            student = user.student_profile
        except StudentProfile.DoesNotExist:
            pass
    try:
        ActivityLog.objects.create(
            user=user,
            student=student,
            action=action,
            description=description,
            object_type="book" if book else "",
            object_id=str(book.pk) if book else "",
        )
    except DatabaseError:
        pass


def home(request):
    return render(request, "landing/home.html")


def discover(request):
    books = _catalogue()
    query = request.GET.get("q", "").strip()
    category = request.GET.get("category", "").strip()
    if query:
        books = [item for item in books if query.casefold() in f"{item['title']} {item['author']} {item['kind']} {item.get('isbn', '')}".casefold()]
        if request.user.is_authenticated:
            _log(request.user, ActivityLog.Action.SEARCH, f"Searched catalogue for {query[:80]}")
    if category:
        books = [item for item in books if category.casefold() in item["kind"].casefold()]
    materials = []
    try:
        from .models import DigitalMaterial
        materials = list(DigitalMaterial.objects.filter(is_active=True).select_related("subject").prefetch_related("authors")[:8])
    except DatabaseError:
        pass
    return render(request, "library/discover.html", {"books": books, "query": query, "category": category, "materials": materials})


def book_detail(request, slug="database-system-concepts"):
    book = _book_by_slug(slug)
    recommended = [item for item in _catalogue() if item["slug"] != book["slug"]][:3]
    saved = False
    if request.user.is_authenticated and not request.user.is_staff:
        try:
            profile = _student_profile(request.user)
            saved = SavedResource.objects.filter(reading_list__student=profile, book=book.get("record")).exists() if book.get("record") else False
        except DatabaseError:
            pass
    return render(request, "library/book_detail.html", {"book": book, "books": recommended, "is_saved": saved})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:librarian" if request.user.is_staff else "core:student")
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            messages.success(request, f"Welcome back, {user.first_name or user.username}.")
            return redirect("core:librarian" if user.is_staff else "core:student")
        messages.error(request, "Those sign-in details didn't match an account.")
    return render(request, "auth/login.html")


def register(request):
    if request.user.is_authenticated:
        return redirect("core:student")
    if request.method == "POST":
        first_name = request.POST.get("first_name", "").strip()[:150]
        last_name = request.POST.get("last_name", "").strip()[:150]
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        student_id = request.POST.get("student_id", "").strip()[:32]
        department = request.POST.get("department", "").strip()[:100]
        if not all((first_name, username, email, password, student_id)):
            messages.error(request, "Please complete all required fields.")
        elif password != password_confirm:
            messages.error(request, "The passwords do not match.")
        elif len(password) < 8:
            messages.error(request, "Use a password with at least 8 characters.")
        elif User.objects.filter(Q(username__iexact=username) | Q(email__iexact=email)).exists():
            messages.error(request, "That username or email is already registered.")
        elif StudentProfile.objects.filter(student_id=student_id).exists():
            messages.error(request, "That student ID is already registered.")
        else:
            try:
                with transaction.atomic():
                    user = User.objects.create_user(username=username, email=email, password=password, first_name=first_name, last_name=last_name)
                    StudentProfile.objects.create(user=user, student_id=student_id, department=department)
                    ReadingList.objects.create(student=user.student_profile, name="My reading list", is_default=True)
                login(request, user)
                messages.success(request, "Your LibTrack account is ready.")
                return redirect("core:student")
            except (IntegrityError, ValidationError):
                messages.error(request, "We couldn't create that account. Check the details and try again.")
    return render(request, "auth/register.html")


@login_required
def logout_view(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("core:home")


@login_required
def student_dashboard(request):
    profile = _student_profile(request.user)
    active_loans = []
    saved_resources = []
    due_soon = 0
    try:
        active_loans = list(profile.loans.filter(status__in=[Loan.Status.ISSUED, Loan.Status.OVERDUE]).select_related("copy__book").order_by("due_at"))
        saved_resources = list(SavedResource.objects.filter(reading_list__student=profile).select_related("book", "material")[:12])
        due_soon = sum(1 for loan in active_loans if loan.due_at <= timezone.now() + timedelta(days=7))
    except DatabaseError:
        pass
    books = _catalogue()
    return render(request, "student/dashboard.html", {
        "books": books,
        "profile": profile,
        "active_loans": active_loans,
        "active_loan_count": len(active_loans),
        "due_soon": due_soon,
        "saved_resources": saved_resources,
        "saved_count": len(saved_resources),
    })


def _staff_check(user):
    return user.is_authenticated and user.is_staff


@user_passes_test(_staff_check, login_url="core:login")
def librarian_dashboard(request):
    stats = {"total_books": 0, "student_count": 0, "current_loans": 0, "overdue_count": 0, "pending_requests": 0}
    recent_activity = []
    popular_books = []
    try:
        stats["total_books"] = Book.objects.filter(is_active=True).count()
        stats["student_count"] = StudentProfile.objects.count()
        stats["current_loans"] = Loan.objects.filter(status__in=[Loan.Status.ISSUED, Loan.Status.OVERDUE]).count()
        stats["overdue_count"] = Loan.objects.filter(Q(status=Loan.Status.OVERDUE) | Q(status=Loan.Status.ISSUED, due_at__lt=timezone.now())).count()
        stats["pending_requests"] = Reservation.objects.filter(status=Reservation.Status.QUEUED).count()
        popular_books = list(Book.objects.filter(is_active=True).annotate(loan_count=Count("copies__loans", filter=Q(copies__loans__status__in=[Loan.Status.ISSUED, Loan.Status.RETURNED, Loan.Status.OVERDUE]))).order_by("-loan_count")[:5])
        recent_activity = list(ActivityLog.objects.select_related("student__user", "user").order_by("-occurred_at")[:6])
    except DatabaseError:
        pass
    return render(request, "librarian/dashboard.html", {"books": _catalogue(), "stats": stats, "recent_activity": recent_activity, "popular_books": popular_books})


@login_required
def borrow_book(request, slug):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    book_card = _book_by_slug(slug)
    book = book_card.get("record")
    if not book:
        messages.info(request, "This preview title isn't in the live catalogue yet.")
        return redirect("core:book_detail_slug", slug=slug)
    if request.user.is_staff:
        messages.error(request, "Sign in as a student to borrow books.")
        return redirect("core:book_detail_slug", slug=slug)
    profile = _student_profile(request.user)
    try:
        with transaction.atomic():
            outstanding = profile.loans.select_for_update().filter(status__in=[Loan.Status.ISSUED, Loan.Status.OVERDUE]).count()
            if outstanding >= 5:
                messages.error(request, "You have reached the limit of five active loans.")
            else:
                copy = BookCopy.objects.select_for_update().filter(book=book, status=BookCopy.Status.AVAILABLE).first()
                if not copy:
                    Reservation.objects.get_or_create(student=profile, book=book, status=Reservation.Status.QUEUED)
                    messages.info(request, "No copies are available, so you've joined the reservation queue.")
                else:
                    copy.status = BookCopy.Status.ON_LOAN
                    copy.save(update_fields=["status", "updated_at"])
                    Loan.objects.create(student=profile, copy=copy, issued_at=timezone.now(), due_at=timezone.now() + timedelta(days=14), issued_by=request.user)
                    _log(request.user, ActivityLog.Action.BORROW, f"Borrowed {book.title}", book)
                    messages.success(request, f"{book.title} is checked out. It's due in 14 days.")
    except DatabaseError:
        messages.error(request, "The loan couldn't be recorded. Please try again or ask the librarian.")
    return redirect("core:book_detail_slug", slug=slug)


@login_required
def return_loan(request, loan_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if request.user.is_staff:
        loan_query = Loan.objects.select_related("copy__book", "student__user")
    else:
        loan_query = Loan.objects.select_related("copy__book", "student__user").filter(student__user=request.user)
    loan = get_object_or_404(loan_query, pk=loan_id)
    if loan.status not in (Loan.Status.ISSUED, Loan.Status.OVERDUE):
        messages.info(request, "That loan has already been closed.")
    else:
        with transaction.atomic():
            loan.status = Loan.Status.RETURNED
            loan.returned_at = timezone.now()
            loan.received_by = request.user if request.user.is_staff else None
            loan.save(update_fields=["status", "returned_at", "received_by", "updated_at"])
            copy = loan.copy
            copy.status = BookCopy.Status.AVAILABLE
            copy.save(update_fields=["status", "updated_at"])
            _log(request.user, ActivityLog.Action.RETURN, f"Returned {loan.copy.book.title}", loan.copy.book)
        messages.success(request, f"{loan.copy.book.title} has been returned.")
    return redirect("core:librarian" if request.user.is_staff else "core:student")


@login_required
def save_book(request, slug):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    book = _book_by_slug(slug).get("record")
    if not book:
        messages.info(request, "This preview title isn't in the live catalogue yet.")
        return redirect("core:book_detail_slug", slug=slug)
    profile = _student_profile(request.user)
    reading_list, _ = ReadingList.objects.get_or_create(student=profile, is_default=True, defaults={"name": "My reading list"})
    saved, created = SavedResource.objects.get_or_create(reading_list=reading_list, book=book)
    if created:
        _log(request.user, ActivityLog.Action.SAVE, f"Saved {book.title}", book)
        messages.success(request, "Added to your reading list.")
    else:
        saved.delete()
        messages.info(request, "Removed from your reading list.")
    return redirect("core:book_detail_slug", slug=slug)


@user_passes_test(_staff_check, login_url="core:login")
def librarian_catalogue(request):
    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        isbn = request.POST.get("isbn", "").strip()
        if not title:
            messages.error(request, "A title is required.")
        else:
            try:
                book = Book.objects.create(title=title, isbn=isbn or None, publisher=request.POST.get("publisher", "").strip(), description=request.POST.get("description", "").strip())
                quantity = min(max(int(request.POST.get("copies", "1") or 1), 1), 100)
                for index in range(quantity):
                    BookCopy.objects.create(book=book, accession_number=f"LT-{book.pk:05d}-{index + 1:03d}")
                _log(request.user, ActivityLog.Action.ADMIN, f"Added catalogue title {book.title}", book)
                messages.success(request, f"{book.title} was added with {quantity} available copies.")
            except (DatabaseError, ValueError, IntegrityError):
                messages.error(request, "Could not add the title. Check that its ISBN is unique and the copy count is valid.")
        return redirect("core:librarian_catalogue")
    try:
        books = Book.objects.filter(is_active=True).annotate(available_count=Count("copies", filter=Q(copies__status=BookCopy.Status.AVAILABLE))).order_by("title")
        loans = Loan.objects.filter(status__in=[Loan.Status.ISSUED, Loan.Status.OVERDUE]).select_related("student__user", "copy__book").order_by("due_at")[:50]
    except DatabaseError:
        books, loans = [], []
    return render(request, "librarian/catalogue.html", {"books": books, "loans": loans})
