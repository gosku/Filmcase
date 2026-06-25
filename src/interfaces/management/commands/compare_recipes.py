from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from src.domain.recipes import queries as compare_recipes_uc
from src.domain.recipes.queries import RECIPE_FIELDS


class Command(BaseCommand):
    help = "Compare multiple recipes by ID and show their settings and usage periods."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("recipe_ids", nargs="+", type=int, help="Recipe IDs to compare")

    def handle(self, *args: object, **options: Any) -> None:
        ids = options["recipe_ids"]
        result = compare_recipes_uc.get_recipe_comparison(recipe_ids=ids)

        if result.missing_ids:
            self.stderr.write(f"Recipe IDs not found: {list(result.missing_ids)}")

        if not result.recipes:
            return

        ordered = result.recipes
        col_w = 32

        # ── Header ────────────────────────────────────────────────────────────
        header = f"{'Field':<30}" + "".join(f"  Recipe {r.id:<{col_w - 9}}" for r in ordered)
        self.stdout.write("=" * len(header))
        self.stdout.write(header)
        self.stdout.write("=" * len(header))

        # ── Recipe settings ───────────────────────────────────────────────────
        for field in RECIPE_FIELDS:
            values = [str(getattr(r, field) if getattr(r, field) is not None else "—") for r in ordered]
            all_same = len(set(values)) == 1
            row = f"{field:<30}" + "".join(f"  {v:<{col_w - 2}}" for v in values)
            if not all_same:
                row = self.style.WARNING(row)
            self.stdout.write(row)

        # ── Names ─────────────────────────────────────────────────────────────
        names = [r.name or "(unnamed)" for r in ordered]
        self.stdout.write("-" * len(header))
        self.stdout.write(f"{'name':<30}" + "".join(f"  {n:<{col_w - 2}}" for n in names))

        # ── Usage periods ─────────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * len(header))
        self.stdout.write("USAGE PERIODS")
        self.stdout.write("=" * len(header))

        for r in ordered:
            s = result.stats_by_id.get(r.id)
            self.stdout.write(f"\nRecipe {r.id} ({r.name or 'unnamed'}):")
            if s:
                first = s.first_used.strftime('%Y-%m-%d') if s.first_used else "unknown"
                last = s.last_used.strftime('%Y-%m-%d') if s.last_used else "unknown"
                self.stdout.write(f"  Photos:     {s.photo_count}")
                self.stdout.write(f"  First used: {first}")
                self.stdout.write(f"  Last used:  {last}")
            else:
                self.stdout.write("  No images with date_taken found.")

        # ── Monthly breakdown ─────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * len(header))
        self.stdout.write("MONTHLY PHOTO COUNTS  (year-month | recipe counts)")
        self.stdout.write("=" * len(header))

        month_header = f"{'Month':<12}" + "".join(f"  R{r.id:<{col_w - 3}}" for r in ordered)
        self.stdout.write(month_header)
        self.stdout.write("-" * len(month_header))
        for month, counts in sorted(result.monthly_counts.items()):
            row = f"{month:<12}" + "".join(f"  {counts.get(r.id, 0):<{col_w - 3}}" for r in ordered)
            self.stdout.write(row)
