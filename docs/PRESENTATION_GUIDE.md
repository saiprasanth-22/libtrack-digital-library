# LibTrack presentation guide

This is the simple explanation to use during the college presentation. The
website contains extra work, but the main demonstration only needs four ideas:
**books, students, issue/return, and the dashboard**.

## One-line introduction

LibTrack is a Django and MySQL library management system that stores books,
physical copies, student accounts and borrowing records in a relational
database.

## Demo logins

| Portal | Username | Password |
|---|---|---|
| Student | `student` | `1` |
| Librarian | `admin` | `1` |

## Five-minute walkthrough

1. Open the landing page and click **Enter the Library**.
2. Choose **Student Portal**, sign in, and show the dashboard.
3. Open **Browse Books**, search for a title and open its detail page.
4. Show **My Borrowed Books** to explain due dates and loan history.
5. Sign out, choose **Librarian Portal**, and sign in.
6. Show **Books** and explain add, edit, delete and copy availability.
7. Show **Students** and explain that every loan belongs to one student.
8. Open **Issue / Return**, issue an available copy, then record its return.
9. Return to the dashboard and show that its counts come from the database.

## How the code works

The easiest request flow to remember is:

```text
Browser URL -> urls.py -> views.py -> models.py/MySQL -> HTML template
```

- `core/urls.py` connects each URL to a view.
- `core/views.py` receives the request and prepares data.
- `core/models.py` defines the database tables and relationships.
- `core/services.py` contains the important issue/return business rules.
- `templates/` renders that data as HTML.
- `static/css/` and `static/js/` provide styling and small interactions.

## Main database tables

- **User and StudentProfile** — login details and student information.
- **Book** — title, ISBN, author, subject, semester and description.
- **BookCopy** — each physical copy and whether it is available.
- **Loan** — connects one student to one copy with issue, due and return dates.

A book can have many copies. A student can have many loans. A copy can only
have one active loan at a time.

## Explain one feature: issuing a book

1. The librarian selects a student and a book.
2. Django checks the database for an available physical copy.
3. It creates a `Loan` row with the issue and due dates.
4. It changes that copy's status from available to issued.
5. The updated availability and dashboard count are rendered from the database.

Returning does the reverse: the loan receives a return date and the copy becomes
available again. These updates are performed together so the database cannot be
left half-updated.

## CRUD explanation

CRUD means **Create, Read, Update and Delete**. The librarian demonstrates CRUD
on books: add a book, view/search it, edit its details and delete or deactivate
it when appropriate.

## Short viva answers

**Why Django?** It provides URL routing, authentication, forms, validation,
templates and database access in one Python framework.

**Why MySQL?** Library data is relational: students, books, copies and loans
have clear links and require reliable constraints.

**What is an ORM?** Django's ORM lets Python code query MySQL tables without
writing SQL for every operation.

**Why separate Book and BookCopy?** One title may have several physical copies,
and each copy can have its own availability and loan history.

**How is availability calculated?** From `BookCopy` records whose status is
available, not from a hard-coded number.

**How are overdue books found?** An active loan is overdue when its due date is
earlier than the current date and it has not been returned.

**How are portals protected?** Django authentication checks the login, and staff
permissions restrict librarian pages.

**Is the interface data hard-coded?** No. Book lists, availability, loans,
student details and dashboard totals are queried from the database. Only demo
seed data is preloaded for the presentation.

## If asked about the extra features

The repository also contains academic mappings, reports, digital materials and
an optional Study Buddy foundation. They are extensions, not required for the
core DBMS demonstration, so the main navigation intentionally stays focused.
