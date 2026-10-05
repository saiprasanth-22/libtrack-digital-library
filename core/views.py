"""View layer.

Views stay thin: they gather querysets, hand them to templates and delegate
every circulation side effect to ``core.services`` so the business rules live
in exactly one place.
"""

from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import PasswordChangeView, PasswordChangeDoneView
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import (BookCopyForm, BookForm, BookSearchForm, DigitalMaterialForm,
                    LoanIssueForm, LoginForm, StudentProfileForm, StudentRegistrationForm)
from .models import (ActivityLog, Author, Book, BookCopy, Category, DigitalMaterial,
                     Loan, SavedResource, StudentProfile)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _profile_for(user):
    """Fetch (or lazily create) the student profile attached to a login."""
    profile, _ = StudentProfile.objects.get_or_create(
        user=user, defaults={"student_id": f"STU-{user.pk:06d}", "department": "Unassigned"})
    return profile


def _librarian_required(view):
    """Allow only authenticated staff through."""
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_staff, login_url="core:login")(view)


def _student_required(view):
    """Allow only authenticated non-staff students through."""
    return user_passes_test(
        lambda u: u.is_authenticated and not u.is_staff, login_url="core:login")(view)


def _page(request, queryset, per_page=None):
    paginator = Paginator(queryset, per_page or services.rules()["PAGE_SIZE"])
    return paginator.get_page(request.GET.get("page"))


def _book_queryset(request):
    """Build the catalogue queryset from the current query string."""
    form = BookSearchForm(request.GET or None)
    books = Book.objects.active().with_availability().select_related("subject").prefetch_related(
        "authors", "categories")
    if form.is_valid():
        books = books.searchable(form.cleaned_data.get("q"))
        category = form.cleaned_data.get("category")
        if category:
            books = books.filter(categories=category)
        availability = form.cleaned_data.get("availability")
        if availability == "available":
            books = books.available_only()
        elif availability == "unavailable":
            books = books.unavailable_only()
        sort = form.cleaned_data.get("sort") or "title"
        if sort == "author":
            books = books.order_by("authors__name", "title")
        elif sort == "newest":
            books = books.order_by("-created_at", "title")
        elif sort == "availability":
            books = books.order_by("-featured", "title")
        else:
            books = books.order_by("title")
    return books, form


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------

def home(request):
    """Landing page. Headline numbers come from the database."""
    services.sync_overdue_statuses()
    base = (Book.objects.active().with_availability()
            .prefetch_related("authors", "categories"))
    featured = list(base.filter(featured=True)[:3])
    if len(featured) < 3:
        # Backfill with the newest titles so the hero stage is never empty.
        seen = {book.pk for book in featured}
        for book in base.order_by("-created_at"):
            if book.pk not in seen:
                featured.append(book)
            if len(featured) == 3:
                break
    total_copies = BookCopy.objects.filter(book__is_active=True).count()
    context = {
        "featured_books": featured,
        "total_books": Book.objects.active().count(),
        "total_copies": total_copies,
        "available_copies": BookCopy.objects.filter(
            book__is_active=True, status=BookCopy.Status.AVAILABLE).count(),
        "student_count": StudentProfile.objects.filter(is_active=True).count(),
        "section": "home",
    }
    return render(request, "landing/home.html", context)


def discover(request):
    """Searchable, filterable, sortable, paginated catalogue."""
    books, form = _book_queryset(request)
    page = _page(request, books)
    materials = (DigitalMaterial.objects.filter(is_public=True)
                  .select_related("subject", "book")
                  .prefetch_related("authors", "categories")[:8])
    if request.GET.get("q") and request.user.is_authenticated:
        services.log_action(ActivityLog.Action.SEARCH, user=request.user,
                            description=f"Searched for “{request.GET['q'][:60]}”")
    return render(request, "library/discover.html", {
        "form": form,
        "page_obj": page,
        "books": page.object_list,
        "total_results": page.paginator.count,
        "categories": Category.objects.annotate(
            book_count=Count("books", filter=Q(books__is_active=True), distinct=True)
        ).order_by("name"),
        "materials": materials,
        "section": "discover",
    })


def book_detail(request, slug):
    """One catalogue title with live availability and the borrow actions."""
    book = get_object_or_404(
        Book.objects.active().with_availability()
        .prefetch_related("authors", "categories", "digital_materials"),
        slug=slug)
    related = (Book.objects.active().with_availability()
               .filter(categories__in=book.categories.all())
               .exclude(pk=book.pk).distinct()
               .prefetch_related("authors", "categories")[:3])
    if not related:
        related = (Book.objects.active().with_availability()
                   .exclude(pk=book.pk).order_by("title")[:3])

    saved = False
    student = None
    if request.user.is_authenticated and not request.user.is_staff:
        student = _profile_for(request.user)
        saved = SavedResource.objects.filter(
            reading_list__student=student, book=book).exists()
    ratings = book.reviews.filter(is_published=True)

    context = {
        "book": book,
        "related": related,
        "is_saved": saved,
        "materials": book.digital_materials.filter(is_public=True),
        "rating_average": ratings.aggregate(value=Avg("rating"))["value"],
        "rating_count": ratings.count(),
        "student": student,
        "can_borrow": student.can_borrow if student else False,
        "already_issued": bool(student and Loan.objects.filter(
            student=student, book=book, status__in=Loan.ON_LOAN_STATUSES).exists()),
        "already_requested": bool(student and Loan.objects.filter(
            student=student, book=book, status=Loan.Status.REQUESTED).exists()),
        "active_loan_count": services.active_loan_count(student) if student else 0,
        "section": "discover",
    }
    return render(request, "library/book_detail.html", context)


def materials(request):
    """Public list of permitted digital learning materials."""
    query = (request.GET.get("q") or "").strip()
    items = (DigitalMaterial.objects.filter(is_public=True)
             .select_related("subject", "book").prefetch_related("authors", "categories"))
    if query:
        items = items.filter(Q(title__icontains=query) | Q(description__icontains=query)
                             | Q(authors__name__icontains=query)).distinct()
    page = _page(request, items.order_by("title"))
    return render(request, "library/materials.html", {
        "query": query,
        "page_obj": page,
        "materials": page.object_list,
        "total_results": page.paginator.count,
        "section": "materials",
    })


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def login_view(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = LoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        login(request, user)
        services.log_action(ActivityLog.Action.LOGIN, user=request.user,
                            description="Signed in")
        messages.success(request, f"Welcome back, {user.first_name or user.username}.")
        # Send each role straight to its own home screen.
        landing = "core:librarian" if user.is_staff else "core:student"
        return redirect(request.POST.get("next") or landing)
    return render(request, "auth/login.html", {"form": form})


def register(request):
    if request.user.is_authenticated:
        return redirect("core:dashboard")
    form = StudentRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        services.log_action(ActivityLog.Action.LOGIN, student=_profile_for(user), user=user,
                            description="Registered a new account")
        messages.success(request, "Your LibTrack account is ready.")
        return redirect("core:student")
    return render(request, "auth/register.html", {"form": form})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You have been signed out.")
    return redirect("core:home")


@login_required
def dashboard(request):
    """Send each role to its own home screen."""
    return redirect("core:librarian" if request.user.is_staff else "core:student")


# ---------------------------------------------------------------------------
# Student area
# ---------------------------------------------------------------------------

@_student_required
def student_dashboard(request):
    profile = _profile_for(request.user)
    data = services.student_dashboard_data(profile)
    reading_list = profile.reading_lists.filter(is_default=True).first()
    saved = (SavedResource.objects.filter(reading_list=reading_list)
             .select_related("book", "material")[:12] if reading_list else [])
    return render(request, "student/dashboard.html", {
        "profile": profile,
        "stats": data,
        "active_loan_list": data["active_loan_list"],
        "upcoming_due": data["upcoming_due"],
        "recent_loans": data["recent_loans"],
        "recently_added": data["recently_added"],
        "recent_activity": data["recent_activity"],
        "saved_resources": saved,
        "section": "student",
    })


@_student_required
def student_loans(request):
    """Full borrowing history with status, due dates and renewal actions."""
    profile = _profile_for(request.user)
    services.sync_overdue_statuses()
    loans = Loan.objects.filter(student=profile).select_related("book", "copy")
    tab = request.GET.get("tab", "active")
    if tab == "returned":
        loans = loans.filter(status=Loan.Status.RETURNED)
    elif tab == "overdue":
        loans = loans.filter(status=Loan.ON_LOAN_STATUSES, due_at__lt=timezone.now())
    elif tab == "requested":
        loans = loans.filter(status=Loan.Status.REQUESTED)
    elif tab == "all":
        pass
    else:
        loans = loans.filter(status__in=Loan.ON_LOAN_STATUSES + (Loan.Status.REQUESTED,))
    page = _page(request, loans.order_by("-created_at"))
    return render(request, "student/loans.html", {
        "profile": profile,
        "tab": tab,
        "page_obj": page,
        "loans": page.object_list,
        "active_count": services.active_loan_count(profile),
        "max_loans": services.rules()["MAX_ACTIVE_LOANS"],
        "section": "student",
    })


@_student_required
def student_profile(request):
    profile = _profile_for(request.user)
    history = (Loan.objects.filter(student=profile).select_related("book", "copy")
               .order_by("-created_at"))
    return render(request, "student/profile.html", {
        "profile": profile,
        "form": StudentProfileForm(instance=profile),
        "password_form": PasswordChangeForm(user=request.user),
        "stats": services.student_dashboard_data(profile),
        "history": history,
        "section": "student",
    })


@_student_required
@require_POST
def student_profile_update(request):
    profile = _profile_for(request.user)
    form = StudentProfileForm(request.POST, instance=profile)
    if form.is_valid():
        form.save()
        messages.success(request, "Your profile has been updated.")
    else:
        messages.error(request, "Please correct the highlighted fields.")
    return redirect("core:student_profile")


class StudentPasswordChangeView(PasswordChangeView):
    """Password change flow provided by Django authentication."""

    success_url = reverse_lazy("core:student_password_done")
    template_name = "student/password_change.html"

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        for field in form.fields.values():
            field.widget.attrs.setdefault("class", "field-input")
        return form

    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Your password has been changed.")
        return response


class StudentPasswordDoneView(PasswordChangeDoneView):
    template_name = "student/password_done.html"


student_password = StudentPasswordChangeView.as_view()
student_password_done = StudentPasswordDoneView.as_view()


# ---------------------------------------------------------------------------
# Circulation actions
# ---------------------------------------------------------------------------

@_student_required
@require_POST
def borrow_book(request, slug):
    book = get_object_or_404(Book, slug=slug, is_active=True)
    profile = _profile_for(request.user)
    try:
        services.borrow_book(profile, book, actor=request.user)
        messages.success(request, f"“{book.title}” is now on loan to you.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("core:book_detail", slug=slug)


@_student_required
@require_POST
def request_book(request, slug):
    book = get_object_or_404(Book, slug=slug, is_active=True)
    profile = _profile_for(request.user)
    try:
        services.request_book(profile, book)
        messages.success(request, f"Request submitted for “{book.title}”. The librarian will review it.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("core:book_detail", slug=slug)


@_student_required
@require_POST
def renew_loan(request, loan_id):
    loan = get_object_or_404(Loan, pk=loan_id, student__user=request.user)
    try:
        services.renew_loan(loan, actor=request.user)
        messages.success(request, f"“{loan.book.title}” is renewed until {loan.due_at:%d %b %Y}.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect(request.POST.get("next") or "core:student_loans")


@login_required
@require_POST
def return_loan(request, loan_id):
    """Students may return their own books; staff may return any book."""
    loans = Loan.objects.select_related("book", "student__user")
    if not request.user.is_staff:
        loans = loans.filter(student__user=request.user)
    loan = get_object_or_404(loans, pk=loan_id)
    try:
        services.return_book(loan, received_by=request.user if request.user.is_staff else None,
                             actor=request.user)
        messages.success(request, f"“{loan.book.title}” has been returned.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect(request.POST.get("next") or "core:dashboard")


@_student_required
@require_POST
def save_book(request, slug):
    book = get_object_or_404(Book, slug=slug)
    profile = _profile_for(request.user)
    created = services.toggle_saved(profile, book)
    messages.success(request, "Added to your reading list." if created
                     else "Removed from your reading list.")
    return redirect(request.POST.get("next") or "core:book_detail", slug=slug)


# ---------------------------------------------------------------------------
# Librarian area
# ---------------------------------------------------------------------------

@_librarian_required
def librarian_dashboard(request):
    data = services.librarian_dashboard_data()
    return render(request, "librarian/dashboard.html", {
        "stats": data,
        "pending_requests": Loan.objects.filter(
            status=Loan.Status.REQUESTED).select_related("student__user", "book")[:6],
        "top_books": (Book.objects.active()
                      .annotate(borrow_count=Count("loans", distinct=True))
                      .order_by("-borrow_count", "title")[:5]),
        "section": "librarian",
    })


@_librarian_required
def librarian_books(request):
    """Catalogue management: list, search and add."""
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES)
        if form.is_valid():
            book = form.save()
            services.add_copies(book, form.cleaned_data.get("total_copies") or 0)
            services.log_action(ActivityLog.Action.ADMIN, user=request.user,
                                description=f"Added catalogue title {book.title}", obj=book)
            messages.success(request, f"“{book.title}” was added to the catalogue.")
            return redirect("core:librarian_books")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = BookForm()

    books = Book.objects.all().with_availability().prefetch_related("authors", "categories")
    term = (request.GET.get("q") or "").strip()
    if term:
        books = books.searchable(term)
    page = _page(request, books.order_by("title"))
    return render(request, "librarian/books.html", {
        "form": form,
        "query": term,
        "page_obj": page,
        "books": page.object_list,
        "total_results": page.paginator.count,
        "section": "librarian",
    })


@_librarian_required
def librarian_book_edit(request, pk):
    book = get_object_or_404(Book.objects.with_availability(), pk=pk)
    if request.method == "POST":
        form = BookForm(request.POST, request.FILES, instance=book)
        if form.is_valid():
            book = form.save()
            requested = form.cleaned_data.get("total_copies")
            if requested is not None:
                current = book.total_copies
                if requested > current:
                    services.add_copies(book, requested - current)
                elif requested < current:
                    # Only copies that are on the shelf may be withdrawn.
                    removable = (book.copies.filter(status=BookCopy.Status.AVAILABLE)
                                 .order_by("-accession_number")[: current - requested])
                    for copy in removable:
                        copy.delete()
            services.log_action(ActivityLog.Action.ADMIN, user=request.user,
                                description=f"Updated {book.title}", obj=book)
            messages.success(request, f"“{book.title}” was updated.")
            return redirect("core:librarian_books")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = BookForm(instance=book)
    return render(request, "librarian/book_form.html", {
        "form": form, "book": book, "is_edit": True, "section": "librarian"})


@_librarian_required
@require_POST
def librarian_book_delete(request, pk):
    """Retire a title instead of deleting it, so loan history survives.

    A title that has never been lent is removed outright, together with its
    physical copies. Anything with borrowing history is only retired.
    """
    from django.db.models import ProtectedError

    book = get_object_or_404(Book, pk=pk)
    title = book.title
    if book.loans.exists():
        book.is_active = False
        book.save(update_fields=["is_active", "updated_at"])
        messages.warning(
            request, f"“{title}” has borrowing history, so it was retired instead of deleted.")
        return redirect("core:librarian_books")

    try:
        with transaction.atomic():
            # Copies protect the book, so they are removed first. A copy that is
            # currently on loan means there is history after all.
            if book.copies.filter(status=BookCopy.Status.ON_LOAN).exists():
                raise ProtectedError("A copy is still on loan.")
            book.copies.all().delete()
            book.delete()
    except ProtectedError:
        book.is_active = False
        book.save(update_fields=["is_active", "updated_at"])
        messages.warning(
            request, f"“{title}” still has copies in circulation, so it was retired instead.")
        return redirect("core:librarian_books")

    messages.success(request, f"“{title}” was deleted.")
    return redirect("core:librarian_books")


@_librarian_required
def librarian_copies(request, pk):
    """Add or edit the physical copies behind one title."""
    book = get_object_or_404(Book.objects.with_availability(), pk=pk)
    if request.method == "POST":
        if request.POST.get("action") == "add":
            services.add_copies(book, 1, shelf_location=request.POST.get("shelf_location", ""))
            messages.success(request, "One copy was added to the shelf.")
        else:
            form = BookCopyForm(request.POST, instance=get_object_or_404(
                BookCopy, pk=request.POST.get("copy_id"), book=book))
            if form.is_valid():
                form.save()
                messages.success(request, "Copy updated.")
            else:
                messages.error(request, "; ".join(
                    "; ".join(e.messages) for e in form.errors.values()))
        return redirect("core:librarian_copies", pk=book.pk)
    copies = book.copies.select_related("book").order_by("accession_number")
    return render(request, "librarian/copies.html", {
        "book": book, "copies": copies,
        "copy_form": BookCopyForm(instance=book.copies.first()),
        "section": "librarian",
    })


@_librarian_required
def librarian_students(request):
    """Search registered students and suspend or restore an account."""
    term = (request.GET.get("q") or "").strip()
    students = StudentProfile.objects.select_related("user").annotate(
        active_loans=Count("loans", filter=Q(loans__status__in=Loan.ON_LOAN_STATUSES),
                           distinct=True),
        total_loans=Count("loans", distinct=True),
    )
    if term:
        students = students.filter(
            Q(student_id__icontains=term) | Q(user__first_name__icontains=term)
            | Q(user__last_name__icontains=term) | Q(user__email__icontains=term)
            | Q(user__username__icontains=term))
    page = _page(request, students.order_by("student_id"), per_page=20)
    return render(request, "librarian/students.html", {
        "query": term, "page_obj": page, "students": page.object_list,
        "total_results": page.paginator.count, "section": "librarian",
    })


@_librarian_required
def librarian_student_detail(request, pk):
    profile = get_object_or_404(StudentProfile.objects.select_related("user"), pk=pk)
    services.sync_overdue_statuses()
    loans = Loan.objects.filter(student=profile).select_related("book", "copy")
    return render(request, "librarian/student_detail.html", {
        "profile": profile,
        "active_loans": loans.filter(status__in=Loan.ON_LOAN_STATUSES),
        "returned_loans": loans.filter(status=Loan.Status.RETURNED),
        "requested_loans": loans.filter(status=Loan.Status.REQUESTED),
        "stats": services.student_dashboard_data(profile),
        "section": "librarian",
    })


@_librarian_required
@require_POST
def librarian_student_toggle(request, pk):
    """Activate or deactivate an account without deleting its history."""
    profile = get_object_or_404(StudentProfile, pk=pk)
    if profile.user_id == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("core:librarian_student_detail", pk=pk)
    profile.is_active = not profile.is_active
    profile.save(update_fields=["is_active", "updated_at"])
    if not profile.is_active:
        profile.user.is_active = False
        profile.user.save(update_fields=["is_active"])
    else:
        profile.user.is_active = True
        profile.user.save(update_fields=["is_active"])
    services.log_action(
        ActivityLog.Action.ADMIN, user=request.user, student=profile,
        description=f"{'Activated' if profile.is_active else 'Deactivated'} {profile.student_id}")
    messages.success(
        request, f"{profile.display_name} is now "
                 f"{'active' if profile.is_active else 'deactivated'}.")
    return redirect("core:librarian_student_detail", pk=pk)


@_librarian_required
def librarian_circulation(request):
    """Issue a book, work through requests and take returns."""
    issue_form = LoanIssueForm(request.POST or None)
    if request.method == "POST" and request.POST.get("action") == "issue":
        if issue_form.is_valid():
            try:
                services.borrow_book(
                    issue_form.cleaned_data["student"], issue_form.cleaned_data["book"],
                    due_at=issue_form.cleaned_data.get("due_at"),
                    issued_by=request.user, notes="Issued at the circulation desk")
                messages.success(request, "Book issued successfully.")
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
        else:
            messages.error(request, "Please correct the issue form.")
        return redirect("core:librarian_circulation")
    if request.method == "POST" and not request.POST.get("action"):
        messages.error(request, "Unknown action.")

    services.sync_overdue_statuses()
    return render(request, "librarian/circulation.html", {
        "issue_form": issue_form,
        "active_loans": Loan.objects.filter(status__in=Loan.ON_LOAN_STATUSES)
        .select_related("student__user", "book")[:50],
        "pending_requests": Loan.objects.filter(status=Loan.Status.REQUESTED)
        .select_related("student__user", "book"),
        "available_copies": Book.objects.active().with_availability()
        .filter(copies__status=BookCopy.Status.AVAILABLE).distinct().order_by("title")[:50],
        "section": "librarian",
    })


@_librarian_required
@require_POST
def librarian_request_approve(request, pk):
    loan = get_object_or_404(Loan, pk=pk, status=Loan.Status.REQUESTED)
    try:
        services.approve_request(loan, issued_by=request.user, actor=request.user)
        messages.success(request, f"Request approved for {loan.student.display_name}.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("core:librarian_circulation")


@_librarian_required
@require_POST
def librarian_request_reject(request, pk):
    loan = get_object_or_404(Loan, pk=pk, status=Loan.Status.REQUESTED)
    try:
        services.reject_request(loan, reason=request.POST.get("reason", "Declined by librarian"),
                                actor=request.user)
        messages.info(request, "Request declined.")
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("core:librarian_circulation")


@_librarian_required
def librarian_materials(request):
    """Add, edit and remove digital materials."""
    if request.method == "POST":
        form = DigitalMaterialForm(request.POST, request.FILES)
        if form.is_valid():
            material = form.save()
            services.log_action(ActivityLog.Action.ADMIN, user=request.user,
                                description=f"Added material {material.title}", obj=material)
            messages.success(request, f"“{material.title}” was added.")
            return redirect("core:librarian_materials")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = DigitalMaterialForm()
    materials_qs = (DigitalMaterial.objects.select_related("subject", "book")
                    .prefetch_related("categories", "authors").order_by("title"))
    page = _page(request, materials_qs, per_page=20)
    return render(request, "librarian/materials.html", {
        "form": form, "page_obj": page, "materials": page.object_list,
        "section": "librarian",
    })


@_librarian_required
def librarian_material_edit(request, pk):
    material = get_object_or_404(DigitalMaterial, pk=pk)
    if request.method == "POST":
        form = DigitalMaterialForm(request.POST, request.FILES, instance=material)
        if form.is_valid():
            form.save()
            messages.success(request, f"“{material.title}” was updated.")
            return redirect("core:librarian_materials")
        messages.error(request, "Please correct the highlighted fields.")
    else:
        form = DigitalMaterialForm(instance=material)
    return render(request, "librarian/material_form.html", {
        "form": form, "material": material, "is_edit": True, "section": "librarian"})


@_librarian_required
@require_POST
def librarian_material_delete(request, pk):
    material = get_object_or_404(DigitalMaterial, pk=pk)
    title = material.title
    material.delete()
    messages.success(request, f"“{title}” was removed.")
    return redirect("core:librarian_materials")


@_librarian_required
def librarian_reports(request):
    """Database-backed reports for the library."""
    now = timezone.now()
    start = request.GET.get("start")
    end = request.GET.get("end")
    from datetime import datetime, timedelta
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.get_current_timezone()) if start else now - timedelta(days=30)
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(tzinfo=timezone.get_current_timezone()) + timedelta(days=1) if end else now
    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt
    data = services.librarian_report_data(start_dt, end_dt)
    return render(request, "librarian/reports.html", {
        "report": data, "start_value": start or "", "end_value": end or "",
        "section": "librarian",
    })
