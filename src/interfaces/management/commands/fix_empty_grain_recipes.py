from django.core.management.base import BaseCommand

from src.application.usecases.recipes import fix_empty_grain_recipes as fix_uc


class Command(BaseCommand):
    help = (
        "Fix FujifilmRecipe rows where grain_roughness is 'Off' but grain_size is '' "
        "(empty string). Rows are either updated in place or merged into an existing "
        "correct row, with images reassigned before deletion."
    )

    def handle(self, *args, **options):
        result = fix_uc.fix_empty_grain_recipes()

        for recipe_id in result.updated_in_place:
            self.stdout.write(f"Updated recipe #{recipe_id}: grain_size set to 'Off'.")

        for recipe_id in result.merged:
            self.stdout.write(
                f"Merged recipe #{recipe_id}: images reassigned to correct row, buggy row deleted."
            )

        total = len(result.updated_in_place) + len(result.merged)
        if total == 0:
            self.stdout.write("No recipes with empty grain_size found. Nothing to do.")
        else:
            self.stdout.write(self.style.SUCCESS(
                f"Done. {len(result.updated_in_place)} updated in place, "
                f"{len(result.merged)} merged."
            ))
