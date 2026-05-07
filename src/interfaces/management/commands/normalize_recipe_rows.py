from typing import Any

from django.core.management.base import BaseCommand

from src.application.usecases.recipes import normalize_recipe_rows as normalize_uc


class Command(BaseCommand):
    help = (
        "Normalize FujifilmRecipe rows by setting inapplicable fields to their "
        "canonical absent value (NULL or empty string). Rows whose normalized shape "
        "already exists as another row are merged: images are reassigned and the "
        "dirty row is deleted. Rows with missing required fields are skipped."
    )

    def handle(self, *args: object, **options: Any) -> None:
        result = normalize_uc.normalize_recipe_rows()

        for normalized in result.normalized:
            fields = ", ".join(normalized.nulled_fields)
            self.stdout.write(f"Updated recipe #{normalized.pk}: nulled {fields}.")

        for merged in result.merged:
            self.stdout.write(
                f"Merged recipe #{merged.pk}: normalized shape matched "
                f"#{merged.merged_into_pk}, images reassigned, row deleted."
            )

        for skipped in result.skipped:
            self.stdout.write(f"Skipped recipe #{skipped.pk}: {skipped.reason}.")

        total_changed = len(result.normalized) + len(result.merged)
        if total_changed == 0 and not result.skipped:
            self.stdout.write("Nothing to do.")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. {len(result.normalized)} updated, "
                f"{len(result.merged)} merged, "
                f"{len(result.skipped)} skipped."
            ))
