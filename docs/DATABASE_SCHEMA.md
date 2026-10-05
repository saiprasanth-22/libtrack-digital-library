# LibTrack — Database Schema

All tables live in the `core` Django app and are created by the migrations in
`core/migrations/`. The runtime database is **MySQL**; a local SQLite fallback
exists only so the project can be demonstrated without a database server.

---

## 1. Entity relationship diagram

```mermaid
erDiagram
    AUTH_USER ||--o| STUDENT_PROFILE : "has profile"
    STUDENT_PROFILE ||--o{ LOAN : "borrows"
    STUDENT_PROFILE ||--o{ READING_LIST : "owns"
    STUDENT_PROFILE ||--o{ REVIEW : "writes"
    STUDENT_PROFILE ||--o{ ACTIVITY_LOG : "triggers"

    BOOK ||--o{ BOOK_COPY : "has physical copies"
    BOOK }o--o{ AUTHOR : "written by"
    BOOK }o--o{ CATEGORY : "classified as"
    BOOK }o--o| SUBJECT : "belongs to"

    BOOK_COPY ||--o{ LOAN : "is lent as"
    BOOK ||--o{ LOAN : "is borrowed as"

    DIGITAL_MATERIAL }o--o| BOOK : "may relate to"
    DIGITAL_MATERIAL }o--o| SUBJECT : "may relate to"
    DIGITAL_MATERIAL }o--o{ CATEGORY : "tagged with"
    DIGITAL_MATERIAL }o--o{ AUTHOR : "written by"

    READING_LIST ||--o{ SAVED_RESOURCE : "contains"
    SAVED_RESOURCE }o--o| BOOK : "may point to"
    SAVED_RESOURCE }o--o| DIGITAL_MATERIAL : "may point to"

    AUTH_USER ||--o{ LOAN : "issued / received"

    AUTH_USER {
        int id PK
        varchar username UK
        varchar email
        varchar password "hashed"
        bool is_staff
        bool is_active
    }

    STUDENT_PROFILE {
        int id PK
        int user_id FK "UNIQUE"
        varchar student_id UK
        varchar department
        int semester
        varchar phone
        int enrollment_year
        bool is_active "borrowing rights"
        datetime created_at
        datetime updated_at
    }

    BOOK {
        int id PK
        varchar slug UK
        varchar title "INDEXED"
        varchar isbn UK
        varchar publisher
        int publication_year
        int page_count
        text description
        varchar cover "image path"
        bool featured "INDEXED"
        bool is_active "INDEXED"
        datetime created_at
        datetime updated_at
    }

    BOOK_COPY {
        int id PK
        int book_id FK
        varchar accession_number UK
        varchar status "available|on_loan|reserved|repair|lost"
        varchar shelf_location
        date acquired_on
    }

    AUTHOR {
        int id PK
        varchar name UK
        text biography
    }

    CATEGORY {
        int id PK
        varchar name UK
        varchar slug UK
        text description
    }

    SUBJECT {
        int id PK
        varchar name UK
        varchar code UK
    }

    LOAN {
        int id PK
        int student_id FK
        int book_id FK
        int copy_id FK "nullable"
        varchar status "REQUESTED|ISSUED|RETURNED|OVERDUE|REJECTED"
        datetime requested_at
        datetime issued_at "nullable"
        datetime due_at "nullable, INDEXED"
        datetime returned_at "nullable"
        int renewal_count
        decimal fine_amount
        int issued_by_id FK
        int received_by_id FK
    }

    DIGITAL_MATERIAL {
        int id PK
        int book_id FK "nullable"
        int subject_id FK "nullable"
        varchar title "INDEXED"
        varchar material_type
        text description
        varchar file "upload path"
        varchar external_url
        bool is_public "INDEXED"
    }

    READING_LIST {
        int id PK
        int student_id FK
        varchar name
        bool is_default
    }

    SAVED_RESOURCE {
        int id PK
        int reading_list_id FK
        int book_id FK "nullable"
        int material_id FK "nullable"
    }

    REVIEW {
        int id PK
        int student_id FK
        int book_id FK
        int rating
        bool is_published
    }

    ACTIVITY_LOG {
        int id PK
        int student_id FK "nullable"
        int user_id FK "nullable"
        varchar action "INDEXED"
        varchar object_type
        varchar object_id
        json metadata
        datetime occurred_at "INDEXED"
    }
```

---

## 2. Tables in words

| Table | Purpose | Rows are protected by |
|---|---|---|
| `auth_user` | Django's built-in login table (salted password hash) | — |
| `core_studentprofile` | Academic details hanging off a user | — |
| `core_author` | One writer, referenced many times | — |
| `core_category` | Subject area shown in catalogue filters | — |
| `core_subject` | Department the book belongs to | — |
| `core_book` | **Bibliographic record** — title, ISBN, publisher, year, cover | `PROTECT` from copies and loans |
| `core_bookcopy` | **One physical copy** — accession number, shelf, status | `PROTECT` from loans |
| `core_loan` | **One borrowing event** — the borrow record | `PROTECT` from student, book, copy |
| `core_digitalmaterial` | Notes, papers, e-books (upload or external URL) | — |
| `core_readinglist` | A student's saved-items list | `CASCADE` from student |
| `core_savedresource` | A book or material inside a reading list | `CASCADE` from list |
| `core_review` | A student's rating and review | `CASCADE` from student and book |
| `core_activitylog` | Audit trail of every action | `SET NULL` (log survives) |

### Primary keys
Every table uses Django's `BigAutoField` named `id`. It is an auto-incrementing
integer, so it is compact, fast to index and never reused.

### Foreign keys and delete behaviour

| Relationship | `on_delete` | Why |
|---|---|---|
| `StudentProfile.user` | `CASCADE` | Deleting the login removes the student record too. |
| `BookCopy.book` | `PROTECT` | A book with physical copies cannot be silently erased. |
| `Loan.student` / `Loan.book` / `Loan.copy` | `PROTECT` | Borrowing history must survive. |
| `DigitalMaterial.book` / `.subject` | `SET_NULL` | Removing a title should not delete a resource. |
| `ReadingList.student`, `SavedResource.reading_list` | `CASCADE` | Purely owned by the student. |
| `ActivityLog.student` / `.user` | `SET_NULL` | The audit trail outlives the account. |

### Many-to-many relationship tables
`Book ↔ Author`, `Book ↔ Category`, `DigitalMaterial ↔ Category`,
`DigitalMaterial ↔ Author` are many-to-many. Django creates join tables
(`core_book_authors`, `core_book_categories`, …). A book can have several
authors (a textbook has three) and several categories, while an author can
appear in many books — this is exactly what a junction table is for.

---

## 3. Integrity rules enforced in the database

These are `CHECK` constraints and `UNIQUE` constraints, so the database itself
refuses bad data even if a view forgets to validate:

| Rule | Where |
|---|---|
| `due_at` is never earlier than `issued_at` | `loan_due_after_issue` |
| `returned_at` is never earlier than `issued_at` | `loan_return_after_issue` |
| A fine is never negative | `loan_fine_nonnegative` |
| A review rating is between 1 and 5 | `review_rating_1_to_5` |
| A student's semester is 1–12 | `student_semester_1_to_12` |
| A digital material has a file **or** a URL | `material_has_a_source` |
| A saved resource points at a book **or** a material, not both/neither | `saved_resource_one_target` |
| ISBN, student number, accession number, slug, category name are unique | `unique=True` |

Indexes were added to every field used in a search or filter:
`Book(title)`, `Book(is_active)`, `Book(featured)`, `BookCopy(book, status)`,
`Loan(student, status)`, `Loan(status, due_at)`, `Loan(book, status)`,
`Loan(created_at)`, `StudentProfile(department, semester)`,
`DigitalMaterial(material_type, is_public)`, `ActivityLog(action, occurred_at)`.

---

## 4. Normalization

The schema is in **Third Normal Form (3NF)**.

**1NF — atomic values.** Every column holds one value. A book does not store
`"A. Silberschatz, Henry Korth, S. Sudarshan"` in an `author` column; the
authors live in `core_author` and are joined through a junction table. There
are no repeating groups such as `copy1_status, copy2_status`.

**2NF — no partial dependency.** In `core_bookcopy`, the primary key is `id`
(a surrogate). `accession_number` is a candidate key. Every non-key column
(`status`, `shelf_location`, `acquired_on`) depends on the *whole* key, not on
part of a composite key, so there is no partial dependency to violate.

**3NF — no transitive dependency.** Non-key columns depend only on the key, not
on other non-key columns. For example, a student's course and semester depend
on `StudentProfile`, not on `User`. Publisher name is stored once on `Book` and
is not re-stored per copy.

**Deliberate denormalisation: none.** There is no cached `available_copies`
column. Availability is *derived* from `BookCopy.status`:

```python
@property
def available_copies(self):
    return self.copies.filter(status=BookCopy.Status.AVAILABLE).count()
```

This means the number physically cannot drift out of step with the copies, and
it can never go negative. A cached counter would be faster but would need
trigger-like logic in every code path — a classic source of data corruption.

---

## 5. Table relationships summary

```
User 1 ─── 0..1 StudentProfile
StudentProfile 1 ─── * Loan
StudentProfile 1 ─── * ReadingList 1 ─── * SavedResource
StudentProfile 1 ─── * Review
StudentProfile 1 ─── * ActivityLog

Book * ─── * Author
Book * ─── * Category
Book * ─── 0..1 Subject
Book 1 ─── * BookCopy 1 ─── * Loan
Book 1 ─── * Loan

DigitalMaterial * ─── * Category
DigitalMaterial * ─── * Author
DigitalMaterial * ─── 0..1 Book
DigitalMaterial * ─── 0..1 Subject
```
