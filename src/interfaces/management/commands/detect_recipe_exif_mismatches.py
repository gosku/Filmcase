"""
Django management command: detect_recipe_exif_mismatches

For each FujifilmRecipe that has associated images with EXIF data, compare
the recipe's tonal fields against the values recorded in FujifilmExif.
Reports recipes where the stored value differs from what the images' EXIF says.

This is useful for finding recipes whose values were rounded when stored
(e.g. highlight -1.5 rounded to -2 due to the old IntegerField).

Usage:
    python manage.py detect_recipe_exif_mismatches
    python manage.py detect_recipe_exif_mismatches --recipe-id 56
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand
from django.db.models import Prefetch

from src.data.models import FujifilmRecipe, Image

# Maps FujifilmRecipe field → FujifilmExif field
_FIELD_MAP: dict[str, str] = {
    "highlight": "highlight_tone",
    "shadow":    "shadow_tone",
    "color":     "color",
    "sharpness": "sharpness",
    "high_iso_nr": "noise_reduction",
    "clarity":   "clarity",
}


def _parse_exif_decimal(raw: str) -> Decimal | None:
    """
    Extract a numeric Decimal from a FujifilmExif string field.

    Handles formats like:
      '-1.5'              → Decimal('-1.5')
      '+1 (medium hard)'  → Decimal('1')
      '0 (normal)'        → Decimal('0')
      'Normal'            → Decimal('0')   (noise_reduction legacy value)
      'Hard' / 'Soft'     → None           (sharpness legacy, no mapping)
      'Film Simulation'   → None           (color on B&W modes)
    """
    if not raw:
        return None
    if raw.lower() == "normal":
        return Decimal("0")
    # Take the first token (before any space) and try to parse it.
    token = raw.split()[0].rstrip(",")
    try:
        return Decimal(token)
    except InvalidOperation:
        return None


class Command(BaseCommand):
    help = (
        "Compare FujifilmRecipe tonal fields against the EXIF data of their "
        "associated images and report mismatches."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--recipe-id",
            type=int,
            default=None,
            metavar="ID",
            help="Only check a single recipe by ID.",
        )
        parser.add_argument(
            "--fix",
            action="store_true",
            help="Update recipe fields to match the EXIF values where unambiguous (single distinct value).",
        )

    def handle(self, *args, **options):
        qs = FujifilmRecipe.objects.prefetch_related(
            Prefetch(
                "images",
                queryset=Image.objects.select_related("fujifilm_exif").exclude(
                    fujifilm_exif__isnull=True
                ),
            )
        )
        if options["recipe_id"]:
            qs = qs.filter(id=options["recipe_id"])

        fix = options["fix"]
        mismatches_found = 0

        for recipe in qs:
            images_with_exif = [img for img in recipe.images.all() if img.fujifilm_exif]
            if not images_with_exif:
                continue

            recipe_mismatches: dict[str, tuple] = {}

            for recipe_field, exif_field in _FIELD_MAP.items():
                recipe_value = getattr(recipe, recipe_field)
                if recipe_value is None:
                    continue

                # Collect distinct EXIF values for this field across all images.
                exif_decimals: set[Decimal] = set()
                for img in images_with_exif:
                    raw = getattr(img.fujifilm_exif, exif_field, "")
                    parsed = _parse_exif_decimal(raw)
                    if parsed is not None:
                        exif_decimals.add(parsed)

                if not exif_decimals:
                    continue

                # Flag if the recipe value is not among the EXIF values seen.
                if Decimal(str(recipe_value)) not in exif_decimals:
                    recipe_mismatches[recipe_field] = (recipe_value, sorted(exif_decimals))

            if recipe_mismatches:
                mismatches_found += 1
                self.stdout.write(
                    self.style.MIGRATE_LABEL(
                        f"\n#{recipe.id}  {recipe.name!r}  ({len(images_with_exif)} images)"
                    )
                )
                fields_to_update = []
                for field, (stored, exif_vals) in recipe_mismatches.items():
                    exif_str = ", ".join(str(v) for v in exif_vals)
                    if len(exif_vals) == 1:
                        new_val = exif_vals[0]
                        if fix:
                            setattr(recipe, field, new_val)
                            fields_to_update.append(field)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"  ✓ {field}: {stored} → {new_val}"
                                )
                            )
                        else:
                            self.stdout.write(
                                self.style.ERROR(
                                    f"  ✗ {field}: stored={stored}  exif={exif_str}"
                                )
                            )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  ? {field}: stored={stored}  exif={exif_str}  (ambiguous — skipped)"
                            )
                        )
                if fix and fields_to_update:
                    recipe.save(update_fields=fields_to_update)

        if mismatches_found == 0:
            self.stdout.write(self.style.SUCCESS("\nNo mismatches found."))
        else:
            self.stdout.write(
                self.style.WARNING(f"\n{mismatches_found} recipe(s) with mismatches.")
            )
