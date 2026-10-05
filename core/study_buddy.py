"""Study Buddy provider boundary.

LibTrack ships the interface and configuration checks for an AI study
companion without shipping any network client. A concrete provider adapter
(anthropic-compatible, openai-compatible, local model gateway...) plugs in by
implementing :class:`StudyBuddyProvider` and being selected through
``STUDY_BUDDY_PROVIDER``. While no key is configured the service reports
itself as unavailable and no HTTP call can happen.
"""

from dataclasses import dataclass, field

from django.conf import settings


@dataclass
class StudyContext:
    """Academic context attached to every request.

    The context constrains answers to the student's own course and the
    library's catalogue; it never carries another student's data.
    """

    course_name: str = ""
    semester: int = None
    subject_name: str = ""
    subject_code: str = ""
    book_title: str = ""
    chapter_topic: str = ""
    mode: str = "explain"
    question: str = ""

    def describe(self) -> str:
        parts = ["Programme: " + (self.course_name or "Not specified")]
        if self.semester:
            parts.append(f"Semester: {self.semester}")
        if self.subject_name:
            parts.append(f"Subject: {self.subject_name}"
                         + (f" ({self.subject_code})" if self.subject_code else ""))
        if self.book_title:
            parts.append(f"Library text in use: {self.book_title}")
        if self.chapter_topic:
            parts.append(f"Chapter/topic: {self.chapter_topic}")
        return "\n".join(parts)


@dataclass
class StudyBuddyResult:
    """One completed interaction, ready for safe rendering."""

    text: str = ""
    mode: str = "explain"
    citations: list = field(default_factory=list)


#: Prompt scaffolding per learning mode. Values are instruction frames only;
#: the academic context and the student's question are appended at call time.
LEARNING_MODES = {
    "explain": "Explain the topic simply for an undergraduate student.",
    "summarize": "Summarise the key points of the topic in exam-ready bullets.",
    "notes": "Turn the topic into structured study notes with headings.",
    "quiz": "Create five short-answer quiz questions with answers.",
    "viva": "Generate eight viva-style questions an examiner could ask.",
    "compare": "Compare the requested concepts in a table of differences and similarities.",
    "revision": "Build a one-week revision plan for the topic.",
}

MODE_CHOICES = tuple(LEARNING_MODES.items())


class StudyBuddyError(Exception):
    """Raised when the configured provider cannot complete a request."""


class StudyBuddyUnavailable(StudyBuddyError):
    """Raised when the feature is disabled or not fully configured."""


def build_prompt(context: StudyContext) -> str:
    """Assemble the deterministic prompt frame for one request.

    The prompt is built from the student-selected context only; it never
    embeds credentials, other students' records or librarian-only data.
    """
    frame = LEARNING_MODES.get(context.mode, LEARNING_MODES["explain"])
    limit = getattr(settings, "STUDY_BUDDY_MAX_INPUT_CHARS", 4000)
    question = (context.question or "")[:limit]
    return (
        "You are Study Buddy, a study companion inside the LibTrack academic "
        "library. Answer only from the academic context provided and the "
        "question. If you are not certain of a fact, say so instead of "
        "guessing. Never reproduce large parts of copyrighted books.\n\n"
        f"{context.describe()}\n\n"
        f"Task: {frame}\n\n"
        f"Question: {question}"
    )


class StudyBuddyProvider:
    """Interface every provider adapter must implement."""

    name = "abstract"

    def generate_response(self, context: StudyContext) -> StudyBuddyResult:
        raise NotImplementedError

    # Convenience wrappers used by the future views.
    def summarize_material(self, context: StudyContext) -> StudyBuddyResult:
        context.mode = "summarize"
        return self.generate_response(context)

    def generate_quiz(self, context: StudyContext) -> StudyBuddyResult:
        context.mode = "quiz"
        return self.generate_response(context)

    def generate_viva_questions(self, context: StudyContext) -> StudyBuddyResult:
        context.mode = "viva"
        return self.generate_response(context)

    def explain_topic(self, context: StudyContext) -> StudyBuddyResult:
        context.mode = "explain"
        return self.generate_response(context)


def is_configured():
    """True only when the feature is switched on and fully configured.

    Reads the settings lazily (rather than at import time) so tests can
    override individual values with ``override_settings``.
    """
    return bool(
        getattr(settings, "STUDY_BUDDY_ENABLED", False)
        and (getattr(settings, "STUDY_BUDDY_PROVIDER", "") or "").strip()
        and (getattr(settings, "STUDY_BUDDY_MODEL", "") or "").strip()
        and (getattr(settings, "STUDY_BUDDY_API_KEY", "") or "").strip()
    )


def get_provider():
    """Return the configured provider, or raise ``StudyBuddyUnavailable``.

    This is the only place a concrete adapter is chosen. While the feature is
    unconfigured this raises before any network activity is possible, so the
    disabled state is enforced in code rather than by convention.
    """
    if not is_configured():
        raise StudyBuddyUnavailable(
            "Study Buddy is not configured. Ask the librarian to set the "
            "STUDY_BUDDY_* environment variables.")
    provider_name = (settings.STUDY_BUDDY_PROVIDER or "").strip().lower()
    if provider_name != "echo":
        # Only the deterministic echo adapter ships with LibTrack; real
        # provider adapters are added when an API key exists.
        raise StudyBuddyUnavailable(f"Unknown Study Buddy provider '{provider_name}'.")
    return EchoProvider()


class EchoProvider(StudyBuddyProvider):
    """Deterministic offline adapter used by the test suite.

    It never touches the network: it returns the constructed prompt so tests
    can assert on exactly what a real adapter would be asked.
    """

    name = "echo"

    def generate_response(self, context: StudyContext) -> StudyBuddyResult:
        return StudyBuddyResult(text=build_prompt(context), mode=context.mode)
