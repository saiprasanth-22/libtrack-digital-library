"""Generate deterministic editorial cover artwork for the catalogue.

    python manage.py generate_covers            # all books with a family
    python manage.py generate_covers --force    # overwrite existing files

Writes one text-free SVG per book under ``static/images/covers/<family>/`` and
updates ``static/images/covers/manifest.json``. Output is stable for a given
slug: the same book always produces the same artwork, and no readable
typography is ever rasterised - titles are applied by HTML/CSS.
"""

import json

from django.core.management.base import BaseCommand

from core import cover_art
from core.cover_art import CANVAS_HEIGHT, CANVAS_WIDTH, FAMILIES, PALETTES
from core.models import Book


# ---------------------------------------------------------------------------
# SVG primitives (all coordinates on a 1200x1800 canvas, art centred low so
# the upper third stays clear for HTML/CSS title typography)
# ---------------------------------------------------------------------------

def _svg_open(palette):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" '
            f'height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}">'
            f'<rect width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" '
            f'fill="{palette["background"]}"/>')


def _grid(palette, variant, seed):
    """Modular grid marks - programming / web families."""
    step = 120 + variant * 40
    rows = []
    for x in range(step, CANVAS_WIDTH - step // 2, step):
        for y in range(860, CANVAS_HEIGHT - 160, step):
            size = 26 + (seed + x + y) % 34
            fill = palette["accent"] if (x + y) % (step * 2) < step else palette["accent_soft"]
            opacity = "0.55" if (seed + x) % 3 else "0.85"
            rows.append(f'<rect x="{x}" y="{y}" width="{size}" height="{size}" '
                        f'rx="8" fill="{fill}" opacity="{opacity}"/>')
    return "".join(rows)


def _network(palette, variant, seed):
    """Connected nodes and edges - algorithms / networking / marketing."""
    import random
    rng = random.Random(seed + variant)
    points = [(rng.randint(100, CANVAS_WIDTH - 100),
               rng.randint(880, CANVAS_HEIGHT - 180)) for _ in range(9 + variant * 3)]
    edges = []
    for i, (x1, y1) in enumerate(points):
        for x2, y2 in points[i + 1:]:
            if abs(x1 - x2) + abs(y1 - y2) < 420:
                edges.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                             f'stroke="{palette["accent_soft"]}" stroke-width="2" '
                             f'opacity="0.35"/>')
    nodes = "".join(
        f'<circle cx="{x}" cy="{y}" r="{14 + (seed + i) % 12}" '
        f'fill="{palette["accent"] if i % 2 else palette["paper"]}" opacity="0.9"/>'
        for i, (x, y) in enumerate(points))
    return "".join(edges) + nodes


def _relational(palette, variant, seed):
    """Linked record rows - databases family."""
    rows = []
    width, height = 880, 64 + variant * 8
    top = 900 + variant * 40
    for index in range(6):
        y = top + index * (height + 28)
        fill = palette["paper"] if index % 2 == 0 else palette["accent_soft"]
        opacity = "0.16" if index % 2 else "0.3"
        rows.append(f'<rect x="{(CANVAS_WIDTH - width) // 2}" y="{y}" width="{width}" '
                    f'height="{height}" rx="14" fill="{fill}" opacity="{opacity}"/>')
        for cell in range(2 + variant):
            cx = 220 + cell * (640 // (2 + variant))
            rows.append(f'<circle cx="{cx}" cy="{y + height // 2}" r="10" '
                        f'fill="{palette["accent"]}" opacity="0.85"/>')
    return "".join(rows)


def _layers(palette, variant, seed):
    """Stacked system layers - operating systems / cloud."""
    shapes = []
    top = 920 + variant * 30
    for index in range(4 + variant):
        y = top + index * 130
        inset = index * 46
        fill = palette["accent"] if index % 2 else palette["accent_soft"]
        shapes.append(f'<rect x="{140 + inset}" y="{y}" '
                      f'width="{CANVAS_WIDTH - 280 - inset * 2}" height="88" '
                      f'rx="18" fill="{fill}" opacity="{0.75 - index * 0.1:.2f}"/>')
    return "".join(shapes)


def _curves(palette, variant, seed):
    """Statistical curves and plotted marks - data science / mathematics."""
    import math
    paths = []
    for series in range(2 + variant):
        d = []
        for step in range(21):
            x = 120 + step * 48
            phase = series * 1.3 + (seed % 7) * 0.35
            y = 1250 - int(330 * math.sin(phase + step / 3.1) * (0.6 + 0.1 * series)) \
                - series * 90
            d.append(f"{'M' if step == 0 else 'L'}{x},{y}")
        stroke = palette["accent"] if series == 0 else palette["accent_soft"]
        paths.append(f'<path d="{" ".join(d)}" fill="none" stroke="{stroke}" '
                     f'stroke-width="{8 - series * 2}" opacity="0.8"/>')
    marks = "".join(
        f'<circle cx="{140 + i * 96}" cy="{1210 - (i * 53 + seed) % 320}" r="9" '
        f'fill="{palette["paper"]}" opacity="0.7"/>' for i in range(10))
    return "".join(paths) + marks


def _plans(palette, variant, seed):
    """Architectural dependency plans - software engineering."""
    shapes = []
    top = 920 + variant * 36
    for index in range(5):
        y = top + index * 128
        width = 900 - index * 120
        shapes.append(f'<rect x="{(CANVAS_WIDTH - width) // 2}" y="{y}" width="{width}" '
                      f'height="86" rx="12" fill="none" stroke="{palette["accent_soft"]}" '
                      f'stroke-width="3" opacity="0.55"/>')
        shapes.append(f'<line x1="{(CANVAS_WIDTH - width) // 2 + 60}" y1="{y}" '
                      f'x2="{(CANVAS_WIDTH - width) // 2 + 60}" y2="{y + 86}" '
                      f'stroke="{palette["accent"]}" stroke-width="3" opacity="0.7"/>')
    return "".join(shapes)


def _lattice(palette, variant, seed):
    """Controlled lattice and boundary - cybersecurity."""
    cells = []
    size = 96 + variant * 12
    for x in range(140, CANVAS_WIDTH - 140, size):
        for y in range(880, CANVAS_HEIGHT - 160, size):
            filled = (x // size + y // size + seed) % 4 == 0
            if filled:
                cells.append(f'<rect x="{x}" y="{y}" width="{size - 14}" '
                             f'height="{size - 14}" rx="10" fill="{palette["accent"]}" '
                             f'opacity="0.6"/>')
            else:
                cells.append(f'<rect x="{x}" y="{y}" width="{size - 14}" '
                             f'height="{size - 14}" rx="10" fill="none" '
                             f'stroke="{palette["accent_soft"]}" stroke-width="2" '
                             f'opacity="0.35"/>')
    border = (f'<rect x="120" y="860" width="{CANVAS_WIDTH - 240}" '
              f'height="{CANVAS_HEIGHT - 1040}" rx="26" fill="none" '
              f'stroke="{palette["paper"]}" stroke-width="4" opacity="0.5"/>')
    return "".join(cells) + border


MOTIFS = {
    "programming": _grid,
    "web": _grid,
    "mobile": _grid,
    "algorithms": _network,
    "networking": _network,
    "marketing": _network,
    "employability": _network,
    "databases": _relational,
    "operating-systems": _layers,
    "cloud": _layers,
    "data-science": _curves,
    "mathematics": _curves,
    "software-engineering": _plans,
    "artificial-intelligence": _network,
    "cybersecurity": _lattice,
    "business": _relational,
}


def build_svg(slug, family):
    """Render one text-free cover SVG for a slug + family."""
    palette = PALETTES[cover_art.art_spec(slug, family)["palette"]]
    spec = cover_art.art_spec(slug, family)
    motif = MOTIFS[family]
    return (_svg_open(palette)
            + motif(palette, spec["variant"], spec["seed"] % 1000)
            + f'<rect width="{CANVAS_WIDTH}" height="{CANVAS_HEIGHT}" fill="none" '
              f'stroke="{palette["paper"]}" stroke-opacity="0.18" stroke-width="6"/>'
            + '</svg>')


class Command(BaseCommand):
    help = "Generate deterministic text-free SVG cover artwork."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true",
                            help="Regenerate files that already exist.")
        parser.add_argument("--family", default="",
                            help="Limit generation to one subject family.")

    def handle(self, *args, **options):
        force = options["force"]
        only_family = options["family"].strip().lower()
        out_root = cover_art.manifest_path().parent
        books = Book.objects.active().prefetch_related("categories")
        manifest = {"version": 1, "method": "deterministic-svg",
                    "license": "Original LibTrack artwork, generated at build time; "
                               "no third-party or scraped material.",
                    "covers": {}}
        existing = {}
        manifest_file = out_root / "manifest.json"
        if manifest_file.exists() and not force:
            try:
                existing = json.loads(manifest_file.read_text(encoding="utf-8"))
            except ValueError:
                existing = {}

        written = skipped = 0
        for book in books:
            family = cover_art.family_for_book(book)
            if only_family and family != only_family:
                continue
            spec = cover_art.art_spec(book.slug, family)
            relative = f"covers/{family}/{book.slug}.svg"
            target = out_root / family / f"{book.slug}.svg"
            if target.exists() and not force and book.slug in existing.get("covers", {}):
                manifest["covers"][book.slug] = existing["covers"][book.slug]
                skipped += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(build_svg(book.slug, family), encoding="utf-8")
            manifest["covers"][book.slug] = {
                "file": f"images/{relative}",
                "family": family,
                "palette": spec["palette"],
                "variant": spec["variant"],
                "alt": cover_art.alt_text(book),
                "provenance": "Original deterministic LibTrack artwork (SVG, text-free).",
            }
            written += 1

        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False),
                                 encoding="utf-8")
        cover_art.reload_manifest()
        self.stdout.write(self.style.SUCCESS(
            f"Cover generation complete: {written} written, {skipped} reused, "
            f"{manifest_file} updated."))
