# Study Buddy architecture

Study Buddy is LibTrack's future AI study companion. The feature ships
**fully scaffolded but disabled**: the interface, the academic context model,
the provider boundary and the tests exist today, and no network call is
possible until a librarian configures an API key.

## Current status

| component | status |
|---|---|
| Page + context selectors (`/study-buddy/`) | live, students only |
| Disabled state ("Awaiting configuration") | live, honest and explanatory |
| Provider interface (`StudyBuddyProvider`) | implemented |
| Echo adapter (deterministic, offline, tests only) | implemented |
| Real AI provider adapters | **not implemented — needs an API key** |
| Any network call while disabled | **impossible** (`get_provider()` raises first) |

## Environment variables

| variable | purpose |
|---|---|
| `STUDY_BUDDY_ENABLED` | `true` switches the feature on (default `false`) |
| `STUDY_BUDDY_PROVIDER` | adapter name; only `echo` ships today |
| `STUDY_BUDDY_MODEL` | model identifier for the chosen provider |
| `STUDY_BUDDY_API_KEY` | secret; server-side only, never rendered, logged or sent to the browser |
| `STUDY_BUDDY_MAX_INPUT_CHARS` | maximum question length (default 4000) |
| `STUDY_BUDDY_DAILY_LIMIT` | answers per student per day (default 20) |

The feature is **ready** only when all four of ENABLED, PROVIDER, MODEL and
API_KEY are set (`core.study_buddy.is_configured()`).

## Interaction model

The future interaction always carries academic context, built from the
database and the signed-in student's own profile:

```
Course → Semester → Subject → Book/material → Chapter/topic → Mode → Question
```

Learning modes: explain simply, summarize, study notes, quiz, viva questions,
compare concepts, revision plan.

## Provider boundary

```python
class StudyBuddyProvider:
    def generate_response(context: StudyContext) -> StudyBuddyResult: ...
    # convenience wrappers: summarize_material, generate_quiz,
    # generate_viva_questions, explain_topic
```

`core.study_buddy.get_provider()` is the single selection point. While the
feature is unconfigured it raises `StudyBuddyUnavailable` **before any
network activity can occur**, so the disabled state is enforced in code, not
by convention. A new provider ships by implementing the interface and adding
its name to the selection in `get_provider()`.

`build_prompt(context)` assembles the deterministic prompt frame: system
rules (answer only from context, admit uncertainty, never reproduce
copyrighted book text) + the academic context + the task + the
length-limited question.

## Safety rules

The future AI must never:

- access another student's data — context is built from the requesting
  student's own profile and public catalogue rows only;
- expose librarian-only information — the view is student-role gated;
- pretend to possess a full copyrighted book — the prompt explicitly forbids
  reproducing book text;
- claim unverified academic facts — the prompt requires admitting
  uncertainty;
- execute HTML or render unsafe Markdown — future output is rendered as
  plain text;
- reveal credentials — the key exists only inside the provider adapter;
  templates receive a boolean, never the key;
- replace core library functionality — borrowing, reservations and search
  are independent of Study Buddy.

## Disabled-mode behaviour

While unconfigured, `/study-buddy/` renders fully (context selectors, mode
picker, explanation of the feature), the "Ask Study Buddy" button is disabled
with an explanatory title, and a status panel lists which environment
variables are missing **without ever displaying a configured key**. Students
see the feature and understand its status; nothing leaks and nothing calls
out.
