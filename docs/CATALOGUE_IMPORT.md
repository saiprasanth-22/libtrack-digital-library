# Academic catalogue import

The scheme-aware BCA catalogue lives in versioned CSV files under `data/bca/`
and is loaded with a single management command:

```bash
python manage.py import_bca_catalogue            # full import
python manage.py import_bca_catalogue --dry-run  # validate + report, no writes
python manage.py import_bca_catalogue --strict   # abort + roll back on any error
python manage.py import_bca_catalogue --source data/bca
```

## Guarantees

- **Idempotent.** Every row is looked up by a natural key (code, slug, name)
  before it is created; a second run with the same data reports
  `unchanged` and writes nothing new.
- **`--dry-run` writes nothing, ever.** The whole run happens inside one
  database transaction that is forcibly rolled back at the end, so even a
  crash mid-run leaves no partial data.
- **`--strict` is atomic.** Any invalid row aborts the import and rolls back
  every change made in that run.
- **Row-level reporting.** Every problem is printed with its file, row label
  and reason, then counted in the summary (`created / updated / unchanged /
  skipped / invalid`).
- **Non-destructive.** The importer never deletes rows. Existing copies,
  loans, reviews and reading lists are untouched; copies are only ever
  *topped up* to the requested count, never removed.
- **Duplicate protection.** Non-empty ISBNs must be unique across the
  catalogue; a conflicting ISBN aborts that row (and, under `--strict`, the
  whole run). Multiple blank ISBNs are fine.

## File format

All files are UTF-8 CSV with a header row. Fields containing commas must be
quoted. Multi-value fields (authors, categories) are separated by `;`.

### courses.csv

| column | required | notes |
|---|---|---|
| code | yes | unique, e.g. `BCA` |
| name | yes | |
| duration_semesters | no | default 6, validated 1–12 |
| description | no | |
| is_active | no | `true`/`false`, default `true` |

### curriculum_schemes.csv

| column | required | notes |
|---|---|---|
| code | yes | unique, e.g. `NEP2020` |
| course_code | yes | must match a course row (same file or database) |
| name | yes | |
| university | no | |
| academic_year_from / academic_year_to | no | a course cannot have two schemes with the same year window |
| verification_status | no | `verified_current`, `verified_syllabus`, `curriculum_supported`, `provisional` |
| source_url | no | |
| notes | no | |
| is_active | no | |

### semesters.csv

| column | required | notes |
|---|---|---|
| scheme_code | yes | |
| number | yes | 1–12, unique per scheme |
| display_name | no | default `Semester N` |
| is_active | no | |

### subjects.csv

| column | required | notes |
|---|---|---|
| scheme_code, semester_number | yes | locate the semester |
| code | yes | unique within its semester |
| name | yes | unique within its semester |
| classification | no | `core`, `elective`, `vocational`, `skill`, `laboratory`, `internship`, `project` |
| confidence | no | same values as scheme `verification_status` |
| description | no | |
| source_url | no | |
| is_active | no | |

### authors.csv

| column | required | notes |
|---|---|---|
| name | yes | unique; matched case-sensitively |
| biography | no | original text only; never copied from publisher material |

### books.csv

| column | required | notes |
|---|---|---|
| slug | yes | unique; also the URL of the detail page |
| title | yes | |
| subtitle | no | |
| authors | yes | `;`-separated; every name must be a real author or the institutional `LibTrack Academic Desk` |
| publisher | no | |
| publication_year | no | |
| edition | no | stored separately from the title |
| isbn | no | leave blank unless verified against the exact edition; never invented |
| language | no | default `English` |
| page_count | no | |
| description | no | original summary; never copied from a publisher |
| categories | no | `;`-separated; created on demand with unique slugs |
| cover_family | no | one of the 16 artwork families (see `docs/COVER_ART.md`) |
| copies | no | target physical copy count; existing copies are never removed |
| shelf_location | no | applied to newly created copies |
| featured | no | `true`/`false` |

### book_subject_mappings.csv

| column | required | notes |
|---|---|---|
| book_slug | yes | must match a book row |
| scheme_code, semester_number, subject_code | yes | locate the subject |
| resource_type | no | `textbook`, `reference`, `study_notes`, `question_bank`, `handbook`, `lab_manual` |
| recommendation_status | no | `prescribed`, `recommended`, `supplementary` — use `prescribed` only when an official syllabus lists the book |
| syllabus_note | no | short note linking the book to a syllabus unit |
| confidence | no | |

One book may map to many subjects; the bibliographic record is never
duplicated for that reason.

### digital_materials.csv

| column | required | notes |
|---|---|---|
| title | yes | |
| material_type | no | `ebook`, `paper`, `notes`, `journal`, `other` |
| scheme_code, semester_number, subject_code | no | link the material to a subject |
| authors | no | `;`-separated |
| external_url | no | required unless a file is attached later |
| description | no | |
| is_public | no | default `true` |

## Correcting the curriculum later

When the student supplies her official timetable or marks card:

1. Edit `data/bca/subjects.csv` — change codes, classifications, or add the
   confirmed Semester VI selection. Remove rows for electives she did not
   take.
2. Run `python manage.py import_bca_catalogue --dry-run` and read the report.
3. Run the import for real. Updated rows are updated in place; subjects that
   were removed from the CSV remain in the database (the importer never
   deletes) and can be deactivated from the librarian Academics page.

Confidence labels should be corrected at the same time: a subject confirmed
by the marks card moves from `curriculum_supported` to `verified_current`.
