"""Study Buddy student-facing views.

The page is fully rendered and navigable while the feature is disabled: it
explains the feature, shows the academic context selectors and states clearly
that no AI key is configured yet. Nothing here can reach the network until
``study_buddy_ready`` returns True.
"""

from django.conf import settings
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render

from . import study_buddy
from .models import Book, Semester, Subject


def _student_required(view):
    return user_passes_test(
        lambda u: u.is_authenticated and not u.is_staff, login_url="core:portal_select")(view)


def _context_choices(user):
    """Academic options offered to one student, all sourced from the DB."""
    profile = getattr(user, "student_profile", None)
    semesters = Semester.objects.filter(is_active=True).select_related(
        "curriculum_scheme__course").order_by(
        "curriculum_scheme__course__code", "number")
    subjects = Subject.objects.filter(is_active=True, semester__isnull=False).select_related(
        "semester__curriculum_scheme__course").order_by("semester__number", "name")
    return {
        "semesters": semesters,
        "subjects": subjects,
        "books": (Book.objects.active().order_by("title")
                  .prefetch_related("subject_mappings")),
        "profile": profile,
    }


@_student_required
@login_required
def study_buddy_home(request):
    """The Study Buddy page: fully rendered, clearly disabled without a key."""
    ready = study_buddy.is_configured()
    choices = _context_choices(request.user)
    selected = {
        "semester": request.GET.get("semester", ""),
        "subject": request.GET.get("subject", ""),
        "book": request.GET.get("book", ""),
        "topic": request.GET.get("topic", ""),
        "mode": request.GET.get("mode", "explain"),
        "question": request.GET.get("question", ""),
    }
    return render(request, "study_buddy/home.html", {
        "section": "study_buddy",
        "study_buddy_ready": ready,
        "mode_choices": study_buddy.MODE_CHOICES,
        "choices": choices,
        "selected": selected,
        "max_chars": settings.STUDY_BUDDY_MAX_INPUT_CHARS,
        "daily_limit": settings.STUDY_BUDDY_DAILY_LIMIT,
    })
