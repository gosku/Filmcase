from django.core.management.base import BaseCommand
from django.db.models import Max, Min, Count

from src.data import models

RECIPE_FIELDS = [
    "film_simulation",
    "dynamic_range",
    "d_range_priority",
    "grain_roughness",
    "grain_size",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "white_balance",
    "white_balance_red",
    "white_balance_blue",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
]


class Command(BaseCommand):
    help = "Compare multiple recipes by ID and show their settings and usage periods."

    def add_arguments(self, parser):
        parser.add_argument("recipe_ids", nargs="+", type=int, help="Recipe IDs to compare")

    def handle(self, *args, **options):
        ids = options["recipe_ids"]
        recipes = {r.id: r for r in models.FujifilmRecipe.objects.filter(id__in=ids)}

        missing = set(ids) - set(recipes.keys())
        if missing:
            self.stderr.write(f"Recipe IDs not found: {sorted(missing)}")

        if not recipes:
            return

        ordered = [recipes[i] for i in ids if i in recipes]
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

        stats = (
            models.Image.objects
            .filter(fujifilm_recipe_id__in=ids, taken_at__isnull=False)
            .values("fujifilm_recipe_id")
            .annotate(
                first_used=Min("taken_at"),
                last_used=Max("taken_at"),
                photo_count=Count("id"),
            )
        )
        stats_by_id = {s["fujifilm_recipe_id"]: s for s in stats}

        for r in ordered:
            s = stats_by_id.get(r.id)
            self.stdout.write(f"\nRecipe {r.id} ({r.name or 'unnamed'}):")
            if s:
                self.stdout.write(f"  Photos:     {s['photo_count']}")
                self.stdout.write(f"  First used: {s['first_used'].strftime('%Y-%m-%d')}")
                self.stdout.write(f"  Last used:  {s['last_used'].strftime('%Y-%m-%d')}")
            else:
                self.stdout.write("  No images with date_taken found.")

        # ── Monthly breakdown ─────────────────────────────────────────────────
        self.stdout.write("\n" + "=" * len(header))
        self.stdout.write("MONTHLY PHOTO COUNTS  (year-month | recipe counts)")
        self.stdout.write("=" * len(header))

        from django.db.models.functions import TruncMonth

        monthly = (
            models.Image.objects
            .filter(fujifilm_recipe_id__in=ids, taken_at__isnull=False)
            .annotate(month=TruncMonth("taken_at"))
            .values("month", "fujifilm_recipe_id")
            .annotate(count=Count("id"))
            .order_by("month")
        )

        # Build a month → {recipe_id: count} map
        months: dict = {}
        for row in monthly:
            key = row["month"].strftime("%Y-%m")
            months.setdefault(key, {})[row["fujifilm_recipe_id"]] = row["count"]

        month_header = f"{'Month':<12}" + "".join(f"  R{r.id:<{col_w - 3}}" for r in ordered)
        self.stdout.write(month_header)
        self.stdout.write("-" * len(month_header))
        for month, counts in sorted(months.items()):
            row = f"{month:<12}" + "".join(f"  {counts.get(r.id, 0):<{col_w - 3}}" for r in ordered)
            self.stdout.write(row)
