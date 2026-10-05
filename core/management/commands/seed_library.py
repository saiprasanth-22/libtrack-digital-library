"""Backwards-compatible alias for :mod:`seed_demo_data`.

The project originally shipped ``seed_library``. Both names now run the same
idempotent seeding logic so existing notes and scripts keep working.
"""

from core.management.commands.seed_demo_data import Command as SeedDemoDataCommand


class Command(SeedDemoDataCommand):
    help = "Alias for `seed_demo_data` (kept so older instructions still work)."
