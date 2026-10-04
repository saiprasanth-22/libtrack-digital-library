# LibTrack — Figma + Codex Implementation Specification

## 0. Product target

LibTrack is a premium digital library management platform for college students and librarians.

The benchmark is **not** “good for a college project.” The benchmark is a funded academic SaaS product with a strong editorial identity — refined enough that ordinary library-management projects feel visibly weaker beside it.

### Core design idea
**Modern academic intelligence built on the visual language of books, paper, archives, and institutional heritage.**

Avoid generic Bootstrap/admin dashboards, purple/blue AI gradients, cyberpunk neon, excessive glassmorphism, CRUD-table-first layouts, random stock photos of students, and emerald used as decoration.

---

## 1. Locked visual references

Use these as source-of-truth references:

1. `01_hero.png` — Landing / Hero
2. `02_discover.png` — Discover
3. `03_book_details.png` — Book Details
4. `04_student_dashboard.png` — Student Dashboard
5. `05_librarian_dashboard.png` — Librarian Dashboard

These are **art direction references**, not raster layouts to clone literally. Recreate their hierarchy, spacing, palette, atmosphere, and interaction language using real components.

When there is ambiguity, prioritize consistency with the hero first.

---

## 2. Brand identity

LibTrack should feel scholarly, calm, premium, technically advanced, trustworthy, institutional without feeling old, and editorial without becoming decorative.

Brand line:
> A smarter academic library, beautifully connected.

Librarian line:
> Manage knowledge. Empower students.

---

## 3. Core design tokens

### Colors

```css
:root {
  --ink-950: #08121D;
  --ink-900: #0B1622;
  --forest-950: #0E2A24;
  --forest-900: #15382F;
  --forest-800: #1C463B;

  --emerald-500: #28B98A;
  --emerald-400: #49CFA3;
  --emerald-200: #A9E8D1;

  --cream-50: #FFF9EE;
  --cream-100: #F7F0E3;
  --cream-200: #F0E5D2;
  --paper: #FFFDF8;

  --brown-900: #33251D;
  --brown-700: #5B4332;
  --brown-500: #7A5E46;
  --brown-300: #B79B7B;

  --warm-gray-700: #625D56;
  --warm-gray-500: #8A8178;
  --warm-gray-300: #B9B0A5;

  --danger: #C65A49;
  --warning: #C88731;
  --success: #25886B;
}
```

### Usage rules

- **Cream/paper**: primary application canvas and editorial surfaces.
- **Deep forest**: sidebars, structural chrome, analytics panels, dark cards.
- **Warm brown**: heritage/detail color only — dividers, chart secondary series, metadata, book accents.
- **Emerald**: functional only — primary CTA, active state, availability, progress, intelligence actions, focus state.
- **Ink**: hero depth, typography, dark backgrounds.

Never turn emerald into a general decorative gradient.

---

## 4. Typography

### Serif
Preferred: **Instrument Serif**  
Fallback: Cormorant Garamond → DM Serif Display → Georgia

Use for display headlines, quotes, large editorial numbers, and conceptual emphasis.

### Sans
Preferred: **Manrope**  
Fallback: Inter → system-ui

Use for navigation, controls, metadata, cards, charts, forms, tables, and body copy.

### Scale

```text
Display XL  72–88 px / 0.95–1.02
Display L   56–64 px
H1          44–52 px
H2          34–40 px
H3          26–30 px
H4          20–24 px
Body L      18 px / 1.55
Body        15–16 px / 1.55
Body S      13–14 px
Label       12–13 px
Eyebrow     10–12 px uppercase / 0.18–0.24em tracking
```

Use serif italic for one meaningful phrase at a time: *intelligently connected*, *worth knowing*, *learning today*, *Empower students*.

---

## 5. Layout system

- Primary viewport: 1440 × ~1024 desktop.
- Main content max width: 1240–1320 px.
- Desktop page padding: 48 px.
- Compact desktop/tablet padding: 32 px.
- Mobile padding: 20 px.
- Grid: 12 columns, 24 px gutters.
- Major section spacing: 72–96 px.

Spacing scale:
```text
4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 80 / 96
```

---

## 6. Shape, borders, shadows

Radii:
```text
8  small
12 controls
16 normal cards
20 feature cards
24 hero / large floating panels
999 pills
```

Light border:
```css
1px solid rgba(51,37,29,.10)
```

Dark border:
```css
1px solid rgba(255,255,255,.08)
```

Paper shadow:
```css
0 1px 2px rgba(51,37,29,.06),
0 14px 40px rgba(51,37,29,.08)
```

Dark elevation:
```css
0 20px 60px rgba(0,0,0,.24)
```

Keep glass effects restrained.

---

## 7. Atmosphere

Allowed:
- faint paper grain
- low-contrast architectural line drawings
- subtle academic grid/catalogue markings
- premium book-cover artwork
- warm library imagery in hero/major transition areas
- archival labels and catalogue numbers

Rules:
- UI remains HTML/CSS/component-first.
- Decorative imagery never harms legibility.
- Do not put a library photograph behind every section.
- No particle effects or neon glow.

---

## 8. Core navigation

Desktop nav:

**Left:** LibTrack mark + wordmark  
**Center:** Discover / Digital Resources / How It Works / About  
**Right:** Search / Sign In or profile / primary action

Behavior:
- transparent over hero
- light/cream variant on product pages
- sticky after scroll
- target height 64–72 px

---

## 9. Button system

### Primary
- emerald fill
- dark ink label
- 44–48 px height
- 12 px radius
- optional right arrow

### Signature secondary: Platform Tour
This component is non-negotiable.

- dark translucent background
- warm thin border
- circular play capsule
- cream text
- subtle premium hover treatment

Interaction:
- border warms slightly
- icon shifts +2 px
- button lifts 1–2 px
- no exaggerated scaling

### Tertiary
Text + arrow only:
- `View all →`
- `Explore collection →`
- `Read paper →`

---

## 10. Signature interaction: global search

Shortcut:
- `⌘ K` macOS
- `Ctrl K` Windows/Linux

Prompt:
> Search books, authors, subjects, ISBNs, or resources…

Search types:
- Books
- Research Papers
- E-Books
- Journals
- Course Material

Optional high-impact mode:
> Ask LibTrack

Example:
> Find beginner-friendly resources for neural networks.

---

# 11. Screen 01 — Landing / Hero

## Goal
Immediate prestige and clear product identity.

### Left
Eyebrow:
`DIGITAL LEARNING, REIMAGINED`

Headline:
> Your entire library,  
> *intelligently connected.*

Support:
> Discover books, access academic resources, and manage your reading journey from one beautifully organized platform.

Actions:
- Explore the Library
- Watch Platform Tour

Micro stats:
- 12K+ books
- 3K students
- Available anytime

### Right product composition
- large global search
- 3 premium book covers
- “Available now” badge
- reading progress card
- weekly activity chart
- recommendation card

### Lower edge
Warm cream transition with headline/statistics beginning to appear.

### Motion
1. nav fades in
2. headline reveals
3. italic phrase/underline draws
4. cards stagger in
5. stats appear last

Target duration: 450–700 ms. No springy gimmicks.

---

## 12. Platform Tour behavior

The tour button must not be decorative.

Preferred interaction:
- hero dims 10–15%
- focused walkthrough opens
- guided sequence: Search → Recommendation → Borrow/Read → Student Dashboard → Librarian Intelligence

This should function as part of the live presentation choreography.

---

# 13. Screen 02 — Discover

## Goal
Prove LibTrack is a full discovery system, not a landing-page mockup.

### Primary layout
Dark forest left navigation plus cream content canvas.

Sidebar:
- All Collections
- Books
- Research Papers
- E-Books
- Journals
- Course Material

Subjects:
- Computer Science
- Electronics
- Mechanical
- Civil Engineering
- Management
- Science
- Humanities
- More Subjects

### Main hero
Headline:
> Discover something  
> *worth knowing.*

Support:
> A curated collection of books, research papers, journals, and academic resources — all in one place.

Then:
- large search bar
- filter chips
- curated collection cards
- Popular Books row
- Research Papers row

Collection cards:
- Recommended for Computer Science
- Recently Added This Week
- Faculty Picks
- Trending on Campus

Optional right student rail:
- identity
- active loans
- due soon
- saved resources
- reading progress
- quick access

Keep the content dense enough to feel real, but preserve breathing room.

---

# 14. Screen 03 — Book Details

## Goal
Make a library record feel like a premium product page.

### Main book area
- large editorial book cover / 3D book presentation
- preview thumbnail rail
- title
- authors
- edition
- ISBN
- publisher
- rating
- academic tags
- concise description

### Availability/status card
Dark forest panel:
- Available now
- library location
- floor
- shelf
- copy count

Actions:
- Borrow Book
- Read Digitally
- Add to Reading List

### Tabs
- Overview
- Contents
- Availability
- Reviews
- Similar Resources

### Lower sections
- About This Book
- learning themes
- related subjects
- student quote/review
- Popular Among Students
- Recommended for You

---

# 15. Screen 04 — Student Dashboard

## Goal
Make the library feel personal and academic rather than administrative.

Greeting:
`GOOD MORNING,`

> Sai.  
> What are we *learning today?*

### Main modules
- global search
- 03 Active Loans
- 01 Due Soon
- 17 Saved Resources
- 72% Reading Progress
- Continue Reading
- Upcoming Due Dates
- Recommended for You
- Explore by Subject

### Right rail
Calendar/schedule:
- lecture
- library visit
- group study

Reading Activity:
- monthly chart
- books read
- reading time
- trend

Contextual recommendation:
> Because you’re studying DBMS

---

# 16. Screen 05 — Librarian Dashboard

## Goal
This is the “we thought beyond CRUD” screen.

Eyebrow:
`LIBRARIAN DASHBOARD`

Headline:
> Manage knowledge.  
> *Empower students.*

Support:
> Track usage, manage resources, and gain insights to build a more engaged academic community.

### KPI row
- Total Books
- Active Students
- Current Loans
- Return Rate

Each KPI includes current value + monthly delta.

### Analytics
- Library Usage Trend
- Resource Distribution
- Recent Activity
- Top Borrowed Books
- Active Loans by Department
- Member Engagement

### Operational cards
- Pending Requests
- Overdue Books
- Maintenance Alerts

### Signature intelligence card
> 23 students searched for “Machine Learning” this week while only 4 copies are available.

Action:
`Consider acquisition →`

This is a key presentation moment.

---

## 17. Data visualization rules

Use:
- forest green primary
- emerald highlight
- warm brown secondary
- cream background
- muted grid lines

Never use:
- rainbow palettes
- default bright blue
- cyan-heavy gradients
- 3D charts
- heavy grid lines

Animation: 500–700 ms ease-out.

---

## 18. Iconography

Use one outline family consistently.

Recommended:
- Lucide
- Phosphor

Stroke: 1.5–1.75 px.

No cartoon icons or mixed icon systems.

---

## 19. Book-cover system

Book covers are a major brand asset.

Direction:
- editorial
- believable academic publishing
- cream / forest / brown / charcoal
- restrained illustration

Examples:
- Algorithms → topographic/mountain/grid motif
- Database Systems → institutional architecture / structured landscape
- Clean Code → branching/tree abstraction
- Networks → topology/geometric connections
- Operating Systems → industrial/architectural abstraction

For public deployment, use original/fictionalized covers rather than copying copyrighted commercial covers.

---

## 20. Responsive behavior

### Tablet
- sidebar collapses
- right rail moves below main content
- book details become 2-column
- analytics reduce to 2-column cards

### Mobile
- single column
- compact navigation
- display serif around 42–52 px
- hero product cards stack beneath copy
- filters horizontally scroll
- charts full-width
- tables become stacked cards

Do not simply shrink desktop UI until it becomes unreadable.

---

## 21. Accessibility

Minimum requirements:
- WCAG AA contrast
- visible focus states
- keyboard navigation
- logical tab order
- 44 px minimum touch target
- reduced-motion support
- semantic headings
- labels for inputs
- aria labels for icon-only controls

---

# 22. Figma construction plan

Create pages:

```text
00 — Foundations
01 — Components
02 — Landing
03 — Discover
04 — Book Details
05 — Student
06 — Librarian
07 — Prototype
```

### Foundations
- palette
- typography
- spacing
- grid
- radii
- shadows
- icon rules

### Components
Build variants for:
- Navbar
- Sidebar
- Button
- Search
- Chip
- Book Card
- Research Card
- KPI Card
- Progress Card
- Chart Card
- Status Badge
- Resource Row
- Calendar Item
- Alert Card
- Tabs
- Platform Tour modal
- Dropdown

Use Auto Layout wherever practical.

Naming examples:
```text
Button/Primary/Default
Button/Primary/Hover
Button/Secondary/Tour
Card/Book/Default
Card/KPI/Light
Card/KPI/Dark
Nav/Desktop/Hero
Sidebar/Student
Sidebar/Librarian
```

---

# 23. Codex implementation stack

Recommended:
- Next.js
- TypeScript
- Tailwind CSS or CSS Modules
- Framer Motion
- Lucide icons
- Recharts
- local mock data first; backend later

Suggested structure:

```text
src/
  app/
    page.tsx
    discover/
    books/[id]/
    student/
    librarian/
  components/
    layout/
    navigation/
    search/
    books/
    dashboard/
    charts/
    ui/
  data/
  lib/
  styles/
```

If Tailwind is used, put brand colors/spacing/type into the theme instead of scattering hex values through components.

---

# 24. Codex rules

Codex must:
1. Match the references before inventing new visual ideas.
2. Build reusable components.
3. Use shared spacing/tokens instead of random values.
4. Preserve serif/sans hierarchy.
5. Preserve cream + forest + brown identity.
6. Use emerald only for meaningful states/actions.
7. Keep realistic product proportions.
8. Build responsive behavior deliberately.
9. Avoid generic admin-dashboard aesthetics.
10. Ask before major visual departures.

---

# 25. Implementation order

### Phase 1 — Foundations
Tokens, typography, navbar, buttons, search, cards.

### Phase 2 — Landing
Hero, responsive hero, platform-tour shell.

### Phase 3 — Discover
Filters, collections, book cards, research cards.

### Phase 4 — Book Details
Book presentation, availability, tabs, recommendations.

### Phase 5 — Student Dashboard
Personal dashboard and reading flows.

### Phase 6 — Librarian Dashboard
Analytics, operational cards, intelligence insight.

### Phase 7 — Polish
Motion, keyboard flow, accessibility, responsive QA, visual QA.

---

# 26. Presentation choreography

Do not start with:
> “This is our library management system.”

Preferred flow:
1. Open hero full-screen.
2. State the problem in one sentence.
3. Click **Explore the Library**.
4. Search a topic.
5. Open a book.
6. Borrow or read digitally.
7. Show Student Dashboard.
8. Switch to Librarian Dashboard.
9. Show the Machine Learning demand insight.
10. End on analytics/intelligence.

The story is:
**Discovery → Access → Personalization → Operations → Intelligence.**

---

# 27. Quality gate

Before calling a screen finished, ask:

- Does it look like the same product as the hero?
- Is cream dominant enough on product pages?
- Is forest green structural rather than decorative?
- Is brown subtle?
- Is emerald rare and meaningful?
- Is serif type used for hierarchy rather than everywhere?
- Is there enough whitespace?
- Does any component look like default Bootstrap?
- Does it still feel premium at 100% zoom?
- Can the screen be built as real reusable components?
- Does the screen give the presenter something worth demonstrating?

If any answer is no, revise before moving on.

---

# 28. Non-negotiable

**LibTrack must never look like a library-management database with a skin on top.**

Every screen should communicate that it is a deliberately designed academic product.
