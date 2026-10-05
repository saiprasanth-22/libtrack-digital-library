"""Deterministic editorial cover-art system.

LibTrack Academic Editions covers are generated as SVG artwork: original,
resolution-independent and text-free. All readable typography (title, author,
edition marker) is applied by the application with HTML/CSS, exactly as the
specification requires, so a generated asset can never contain broken or
misspelled title text.

This module defines the shared vocabulary — subject families, palettes and
motifs — used by the ``generate_covers`` management command, and the manifest
loader the templates use to resolve a book's artwork.
"""

import hashlib
import json
from functools import lru_cache
from pathlib import Path

from django.conf import settings

#: Portrait ratio used everywhere: 2:3 at a 1200x1800 unit canvas.
CANVAS_WIDTH = 1200
CANVAS_HEIGHT = 1800

#: Deep forest, parchment, ink, oxide brown, muted teal and aged gold —
#: the same family of colours as the product palette, tuned for print-like
#: editorial artwork rather than screen gradients.
PALETTES = {
    "forest": {
        "background": "#173c34",
        "ink": "#0f2b25",
        "accent": "#28b98a",
        "accent_soft": "#a9e8d1",
        "paper": "#f7f0e3",
        "meta": "#2c5a4d",
    },
    "ink": {
        "background": "#1d2833",
        "ink": "#131c24",
        "accent": "#49cfa3",
        "accent_soft": "#b7d9cd",
        "paper": "#fff9ee",
        "meta": "#31414f",
    },
    "oxide": {
        "background": "#6b4a34",
        "ink": "#4a3223",
        "accent": "#d8a25f",
        "accent_soft": "#f0d8b4",
        "paper": "#fff9ee",
        "meta": "#7d5b42",
    },
    "parchment": {
        "background": "#e7dcc9",
        "ink": "#33251d",
        "accent": "#25886b",
        "accent_soft": "#7a5e46",
        "paper": "#fffdf8",
        "meta": "#d3c2a8",
    },
    "teal": {
        "background": "#1f4b40",
        "ink": "#143630",
        "accent": "#c8a35f",
        "accent_soft": "#a9e8d1",
        "paper": "#f7f0e3",
        "meta": "#2a5c50",
    },
    "slate": {
        "background": "#283c4f",
        "ink": "#1a2836",
        "accent": "#c8a35f",
        "accent_soft": "#a9c0d8",
        "paper": "#fff9ee",
        "meta": "#35495c",
    },
}

PALETTE_ORDER = ("forest", "ink", "oxide", "parchment", "teal", "slate")

#: Subject families and the visual idea each one encodes. The description is
#: also the source for the ready-to-use raster prompts in docs/COVER_ART.md.
FAMILIES = {
    "programming": "modular grids and punched-card geometry; syntax rhythm as repeated marks",
    "algorithms": "graph networks, layered nodes, trees and mathematical topology",
    "databases": "relational grids, linked records, index-like structured archives",
    "operating-systems": "layered systems, process diagrams, memory blocks, scheduling rhythms",
    "networking": "connected points, routing paths, signal lines and distributed structures",
    "web": "modular frames and responsive spatial systems, browser-like geometry without logos",
    "artificial-intelligence": "inference graphs, symbolic systems, neural layers, decision boundaries",
    "data-science": "statistical curves, distributions, plotted marks and analytical layers",
    "software-engineering": "architectural plans, dependency diagrams, component relationships",
    "cybersecurity": "controlled lattices, keys, boundaries and encrypted structures, no clichés",
    "cloud": "distributed layers and abstract service topology, no literal cartoon clouds",
    "business": "elegant analytical forms; dashboards abstracted into editorial geometry",
    "mobile": "touch-grid proportions, interface layers, device-independent interaction patterns",
    "marketing": "campaign pathways, audience networks and publication systems, no platform logos",
    "mathematics": "curves, matrices, proofs, coordinate fields and geometric constructions",
    "employability": "systems thinking, planning artefacts, milestones and collaborative structures",
}

#: Three motif variants per family keeps adjacent books visibly distinct while
#: staying inside one coherent system.
MOTIF_VARIANTS = 3


def family_for_book(book):
    """Resolve the artwork family for one book.

    Explicit ``cover_family`` wins; otherwise the first category name is
    slugified and matched, and anything unknown falls back to a family chosen
    deterministically from the slug so every card still gets real artwork.
    """
    explicit = (getattr(book, "cover_family", "") or "").strip().lower()
    if explicit in FAMILIES:
        return explicit
    for category in book.categories.all():
        candidate = category.slug.lower()
        if candidate in FAMILIES:
            return candidate
        if candidate == "computer-science":
            return "programming"
        if candidate == "data-systems":
            return "databases"
        if candidate == "artificial-intelligence":
            return "artificial-intelligence"
        if candidate == "software-engineering":
            return "software-engineering"
        if candidate == "electronics":
            return "networking"
        if candidate == "mathematics-and-statistics":
            return "mathematics"
        if candidate == "data-science":
            return "data-science"
        if candidate == "web-development":
            return "web"
        if candidate == "cyber-security":
            return "cybersecurity"
        if candidate == "cloud-computing":
            return "cloud"
        if candidate == "business-intelligence":
            return "business"
        if candidate == "mobile-development":
            return "mobile"
        if candidate == "digital-marketing":
            return "marketing"
        if candidate == "employability-skills":
            return "employability"
        if candidate == "general-studies":
            return "mathematics"
    ordered = sorted(FAMILIES)
    return ordered[seed_for(book.slug or book.title) % len(ordered)]


def seed_for(text):
    """Stable integer seed for a slug, independent of Python's hash salt."""
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:4], "big")


def art_spec(slug, family):
    """Deterministic artwork parameters for one book slug."""
    seed = seed_for(slug)
    palette_name = PALETTE_ORDER[seed % len(PALETTE_ORDER)]
    variant = (seed // 7) % MOTIF_VARIANTS
    rotation = (seed // 13) % 4
    return {
        "family": family,
        "palette": palette_name,
        "variant": variant,
        "rotation": rotation,
        "seed": seed,
    }


def alt_text(book):
    """Descriptive alt text for the artwork (the image is decorative; the
    title is adjacent in the markup, so this describes the artwork itself)."""
    family = family_for_book(book)
    return f"Abstract {family.replace('-', ' ')} artwork for the LibTrack edition cover."


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def manifest_path():
    return Path(settings.BASE_DIR) / "static" / "images" / "covers" / "manifest.json"


@lru_cache(maxsize=1)
def _manifest():
    path = manifest_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def reload_manifest():
    """Clear the cache so a fresh generation is visible without a restart."""
    _manifest.cache_clear()


def cover_path(book):
    """Static-relative path to the generated artwork, or '' when none exists."""
    entry = _manifest().get("covers", {}).get(book.slug)
    return entry.get("file", "") if entry else ""


def cover_alt(book):
    entry = _manifest().get("covers", {}).get(book.slug)
    return entry.get("alt", alt_text(book)) if entry else alt_text(book)
