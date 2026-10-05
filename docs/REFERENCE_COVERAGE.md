# Reference Coverage Matrix

Scope of this document: every function visible in the reference video
(*"Library Management System using Django & MySQL | Complete Project with Source
Code"*, Incognito Sword), mapped onto a working LibTrack action.

The reference is a **Django + MySQL + Bootstrap** CRUD application. LibTrack
deliberately does **not** copy its appearance. It keeps the original premium
LibTrack design (hero, typography, editorial layout, cover artwork, motion) and
implements the *same set of outcomes* with production-grade Django practices.

**Status legend** — every row is one of:

| Status | Meaning |
| --- | --- |
| **Covered** | Equivalent action exists, works, is permission-checked and is covered by at least one automated test. |
| **Covered (hardened)** | Reference behaviour implemented, but deliberately made safer or stricter. The deviation is stated in the row. |
| **Extended** | LibTrack provides something the reference does not, added so a visible control would not be dead. |

Source of truth for the reference's scope: the creator's published feature list
plus the route table of the source repository linked in the video description.
Only **functions** were inspected; no reference code or styling was copied.

---

## 1. Pages and navigation

| # | Reference feature | Reference route | LibTrack route | Role | Status | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| 1.1 | Public home page | `/` | `/` | Public | Covered | `test_catalogue.SearchTests.test_landing_page_lists_database_titles_only` |
| 1.2 | Catalogue browsing | `/` (same page) | `/discover/` | Public | Covered | `test_catalogue.SearchTests.test_filter_by_category` |
| 1.3 | Student login | `/login/` | `/accounts/login/` | Public | Covered | `test_accounts.LoginTests.test_student_login_redirects_to_student_dashboard` |
| 1.4 | Admin login | `/login/` | `/accounts/login/` | Public | Covered | `test_accounts.LoginTests.test_librarian_login_redirects_to_librarian_dashboard` |
| 1.5 | Logout | `/logout/` | `/accounts/logout/` | Any signed-in | Covered (hardened) | `test_accounts.LoginTests.test_logout_requires_post_and_ends_session` — POST only; a GET cannot end a session. |
| 1.6 | Student registration | `add-student/` (admin only) | `/accounts/register/` **and** desk form on `/librarian/students/` | Public + Librarian | Extended | `test_accounts.RegistrationTests.test_registration_creates_user_profile_and_default_reading_list`, `test_librarian.StudentManagementTests.test_librarian_can_register_a_student_at_the_desk` |
| 1.7 | Student dashboard | `/student-dashboard/` | `/student/` | Student | Covered | `test_accounts.RouteProtectionTests.test_dashboard_sends_each_role_to_the_right_place` |
| 1.8 | Admin dashboard | `/admin-dashboard/` | `/librarian/` | Librarian | Covered | `test_librarian.ReportTests.test_dashboard_page_shows_aggregated_numbers` |
| 1.9 | "My books" | `/my-books/` | `/student/loans/` | Student | Covered | `test_circulation.ReturnTests.test_return_view_works_for_the_owning_student` |
| 1.10 | Role landing after login | `/admin-dashboard/` or `/student-dashboard/` | `/librarian/` or `/student/` | Both | Covered | `test_accounts.LoginTests.test_student_login_redirects_to_student_dashboard` |

## 2. Book management and inventory

| # | Reference feature | Reference route | LibTrack route | Role | Status | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| 2.1 | Add book with quantity | `/add-book/` | `/librarian/books/` | Librarian | Covered | `test_librarian.BookManagementTests.test_librarian_can_add_a_book_with_copies` |
| 2.2 | View all books | `/view-books/` | `/librarian/books/` | Librarian | Covered | `test_librarian.BookManagementTests.test_catalogue_search_filters_the_admin_list` |
| 2.3 | Delete book | `/delete-book/<serial>/` | `/librarian/books/<pk>/delete/` | Librarian | Covered (hardened) | `test_librarian.BookManagementTests.test_deleting_a_book_with_history_retires_it_instead` — a title with loan history is retired, never destroyed, so history keeps its meaning. |
| 2.4 | Edit book | *(not in reference)* | `/librarian/books/<pk>/edit/` | Librarian | Extended | `test_librarian.BookManagementTests.test_librarian_can_edit_a_book` |
| 2.5 | Inventory tracking / quantity | `Book.quantity` column | `BookCopy` rows per title, `Book.total_copies` / `available_copies` derived | Librarian | Covered | `test_circulation.InventoryTests.test_counts_stay_correct_across_a_full_cycle` |
| 2.6 | Real-time book availability | `Book.quantity` decremented | `Book.available_copies` property over live copy rows | Public + Student | Covered | `test_catalogue.BookDetailTests.test_availability_label_reflects_database_state`, `test_books.AvailabilityPanelTests.test_availability_reflects_a_copy_leaving_the_shelf` |
| 2.7 | Copy-level stock view | *(not in reference)* | `/books/<slug>/` → **Availability** tab; `/librarian/books/<pk>/copies/` | Public + Librarian | Extended | `test_books.AvailabilityPanelTests.test_panel_lists_every_accession_number`, `test_books.AvailabilityPanelTests.test_status_breakdown_counts_really_add_up` |
| 2.8 | Withdraw copies without going negative | *(implicit)* | `/librarian/books/<pk>/edit/`, `/librarian/books/<pk>/copies/` | Librarian | Covered (hardened) | `test_librarian.BookManagementTests.test_withdrawing_a_copy_that_is_on_loan_never_goes_negative`, `test_circulation.InventoryTests.test_available_copies_can_never_be_negative` |

## 3. Student management

| # | Reference feature | Reference route | LibTrack route | Role | Status | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| 3.1 | Add student | `/add-student/` | `/librarian/students/` (`action=add`) | Librarian | Covered | `test_librarian.StudentManagementTests.test_librarian_can_register_a_student_at_the_desk` |
| 3.2 | View students | `/view-students/` | `/librarian/students/` | Librarian | Covered | `test_librarian.StudentManagementTests.test_librarian_can_search_students` |
| 3.3 | Single student record | *(implied)* | `/librarian/students/<pk>/` | Librarian | Covered | `test_librarian.StudentManagementTests.test_student_detail_shows_borrowing_breakdown` |
| 3.4 | Delete student | `/delete-student/<userid>/` | `/librarian/students/<pk>/delete/` | Librarian | Covered (hardened) | `test_librarian.StudentManagementTests.test_librarian_cannot_delete_a_student` (no history → removed outright, login and reading list included), `test_student_with_history_is_deactivated_instead_of_deleted` (history → suspended, rows preserved) |
| 3.5 | Suspend a student | *(not in reference)* | `/librarian/students/<pk>/toggle/` | Librarian | Extended | `test_librarian.StudentManagementTests.test_librarian_can_deactivate_and_reactivate`, `test_circulation.DeactivatedStudentTests.test_deactivated_student_cannot_borrow` |
| 3.6 | Delete validation | *(none — deletes freely)* | Duplicate student ID and duplicate username both rejected at the desk | Librarian | Covered (hardened) | `test_librarian.StudentManagementTests.test_desk_registration_enforces_the_same_validation` |
| 3.7 | Password safety | *(passwords in plaintext-era forms)* | Hashes only; never rendered in any list | Librarian | Covered (hardened) | `test_librarian.StudentManagementTests.test_student_list_never_shows_a_password` |

## 4. Issue, return and due dates

| # | Reference feature | Reference route | LibTrack route | Role | Status | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| 4.1 | Issue book with availability check | `/issue-book/` | `/books/<slug>/borrow/` (student), `/librarian/circulation/` (desk) | Student + Librarian | Covered | `test_circulation.IssueTests.test_successful_issue_creates_loan_and_consumes_exactly_one_copy`, `test_librarian.CirculationDeskTests.test_librarian_issues_a_book_to_a_student` |
| 4.2 | Availability check before issuing | implicit `quantity > 0` | Transactional copy allocation; refuses with a message, never a 500 | Librarian | Covered | `test_circulation.IssueTests.test_issue_is_refused_when_no_copies_are_available`, `test_librarian.CirculationDeskTests.test_issuing_reports_an_error_instead_of_crashing` |
| 4.3 | Return book | `/return-book/` | `/loans/<id>/return/` (owner or librarian) | Student + Librarian | Covered | `test_circulation.ReturnTests.test_successful_return_increases_available_copies_exactly_once` |
| 4.4 | Automatic quantity update on issue | `Book.quantity -= 1` | `BookCopy` → `ON_LOAN` inside one transaction | System | Covered | `test_circulation.InventoryTests.test_counts_stay_correct_across_a_full_cycle` |
| 4.5 | Automatic quantity update on return | `Book.quantity += 1` | `BookCopy` → `AVAILABLE`, guarded against double-return | System | Covered | `test_circulation.ReturnTests.test_duplicate_return_is_rejected_and_does_not_double_count` |
| 4.6 | Due date tracking | `BookIssue.exp` column | `Loan.due_at` + `LIBRARY_LOAN_DAYS` (14) | System | Covered | `test_circulation.IssueTests.test_due_date_defaults_to_the_configured_loan_period` |
| 4.7 | Overdue indicator | computed in the template | `Loan.OVERDUE` status, synced on every read, plus a fine | System | Covered | `test_circulation.OverdueTests.test_overdue_is_derived_from_due_date`, `test_sync_updates_stale_issued_rows_to_overdue` |
| 4.8 | View all issued books with student details | `/view-issued-books/` | `/librarian/circulation/`, `/librarian/reports/`, `/librarian/students/<pk>/` | Librarian | Covered | `test_librarian.ReportTests.test_reports_page_renders_with_live_figures` |
| 4.9 | Issue a pre-requested title | *(not in reference)* | `/books/<slug>/request/`, `/librarian/requests/<id>/approve/`, `.../reject/` | Student + Librarian | Extended | `test_circulation.RequestApprovalTests.test_request_creates_a_pending_record_without_touching_stock`, `test_approving_a_request_consumes_a_copy` |
| 4.10 | Renewal | *(not in reference)* | `/loans/<id>/renew/` | Student | Extended | `test_circulation.RenewalTests.test_renewal_is_capped_at_the_configured_maximum` |
| 4.11 | Max simultaneous loans | *(not in reference)* | `LIBRARY_MAX_ACTIVE_LOANS` (3) | System | Extended | `test_circulation.IssueTests.test_maximum_active_loans_is_enforced` |
| 4.12 | Custom due date at the desk | *(not in reference)* | `/librarian/circulation/` (optional `due_at`) | Librarian | Extended | `test_librarian.CirculationDeskTests.test_issuing_with_custom_due_date_is_respected` |

## 5. Dashboards and statistics

Every figure below is produced by an aggregate query. No number is written into
a template.

| # | Reference feature | Reference route | LibTrack route | Role | Status | Automated test |
| --- | --- | --- | --- | --- | --- | --- |
| 5.1 | Student dashboard counters | `/student-dashboard/` | `/student/` | Student | Covered | `test_librarian.ReportTests.test_dashboard_counters_match_the_database` |
| 5.2 | Admin dashboard counters | `/admin-dashboard/` | `/librarian/` | Librarian | Covered | `test_librarian.ReportTests.test_dashboard_counters_match_the_database` |
| 5.3 | Most-borrowed list | *(not in reference)* | `/librarian/reports/` | Librarian | Extended | `test_librarian.ReportTests.test_most_borrowed_is_ordered_by_count` |
| 5.4 | Date-range filtering | *(not in reference)* | `/librarian/reports/?start=&end=` | Librarian | Extended | `test_librarian.ReportTests.test_date_range_filter_is_applied` |
| 5.5 | Monthly circulation chart | *(not in reference)* | `/librarian/` (chart) from `monthly_circulation()` | Librarian | Extended | `test_circulation.OverdueTests.test_dashboard_counts_overdue_separately` |
| 5.6 | Overdue watchlist | *(not in reference)* | `/librarian/reports/` | Librarian | Extended | `test_librarian.ReportTests.test_overdue_appears_in_the_report` |

## 6. Reference features deliberately redesigned

The reference contains three unsafe or poorly designed patterns. Per the
project rules the **outcome** is preserved but the **mechanism** is not.

| Reference pattern | Why it is unsafe | LibTrack approach | Automated test |
| --- | --- | --- | --- |
| `/delete-student/<userid>/` hard-deletes a student even when they hold loans | Destroys loan history, so past issues no longer mean anything and reports silently change | Delete outright only when there is no history; otherwise suspend, which blocks login and borrowing but preserves every record | `test_student_with_history_is_deactivated_instead_of_deleted` |
| `/delete-book/<serial>/` removes a book outright | Same problem for the catalogue | Retire (deactivate) a title that has history; remove one that has none | `test_deleting_a_book_with_history_retires_it_instead` |
| Mutating links reachable by `GET` | A prefetch, a crawler or a `<img>` tag can trigger a state change | Every mutating route is `@require_POST` with a CSRF token; a `GET` returns 405 | `test_accounts.LoginTests.test_logout_requires_post_and_ends_session` |

## 7. Extensions that close a dead control

LibTrack's own design contained visible controls with no working action behind
them. These were completed rather than removed, so the premium design stays
intact and nothing on screen is decorative.

| Control | Problem found | Resolution | Automated test |
| --- | --- | --- | --- |
| Book detail tab strip (Overview / Availability / Digital resources / Reviews) | Four buttons with no handler — pure decoration | Real ARIA tablist with roving tabindex, arrow-key navigation and deep links; all four panels are in the HTML and stay visible without JavaScript | `test_books.TabPanelTests.*` (3 tests) |
| **Reviews** tab | `Review` rows could never be created, so the tab was permanently empty | Students who have borrowed and returned a title can rate 1–5 and comment; one review per student per title, enforced by a unique constraint; the average and count feed the tab badge | `test_books.ReaderReviewTests.*` (9 tests) |
| **Availability** tab | Tab existed with no content | Live copy-level table with real status, shelf and acquisition data | `test_books.AvailabilityPanelTests.*` (4 tests) |
| Librarian "add student" | Reference had it, LibTrack did not | Registration form on the students page reusing the student-facing validation | `test_librarian_can_register_a_student_at_the_desk` |
| Librarian "delete student" | Reference had it, LibTrack did not | Safe delete/suspend view | `test_librarian.StudentManagementTests` (4 delete tests) |

## 8. Security hardening found during this pass

| Issue | Detail | Resolution | Automated test |
| --- | --- | --- | --- |
| Open redirect | Four views redirected to a client-supplied `next`, including the login form | `_safe_next()` validates the host and scheme via `url_has_allowed_host_and_scheme` | `test_books.OpenRedirectTests.*` (6 tests) |
| Orphaned login | Deleting a `StudentProfile` left the auth `User` row behind, because `CASCADE` only flows parent → child | Delete the `User` and let it cascade down; `Loan.student` is `PROTECT`, so a survivor still triggers the safe fallback | `test_librarian_cannot_delete_a_student` |
| Suspended but still able to sign in | The `ProtectedError` fallback cleared `profile.is_active` but not `user.is_active`, which is what actually gates authentication | Suspend both rows | `test_student_blocked_by_protected_records_can_no_longer_log_in` |

## 9. Coverage summary

| Metric | Value |
| --- | --- |
| Matrix rows (reference functions + extensions) | 43 |
| Reference functions identified | 31 |
| — implemented directly | 25 |
| — implemented with deliberate hardening | 6 |
| **Uncovered** | **0** |
| Extensions added beyond the reference | 12 |
| Automated tests in the suite | 167 |
| Routes returning 4xx/5xx for any of the 3 roles | 0 |
| Decorative dead buttons | 0 |

**Verification commands**

```bash
python manage.py test          # 167 tests, exit 0
python manage.py check         # no issues
python manage.py makemigrations --check --dry-run   # No changes detected
```

## 10. Known limitations

- Migrations and queries are exercised against SQLite in the test suite. The
  MySQL path is verified at the configuration layer only (engine, `utf8mb4`,
  `STRICT_TRANS_TABLES`, PyMySQL), because no MySQL server is available in the
  authoring environment.
- The reference video's spoken narration could not be transcribed; the scope
  above is derived from the creator's published feature list and the route
  table of the source repository linked in the video description. Both were
  checked against the finished application route by route.
