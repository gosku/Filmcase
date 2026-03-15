from django.core.management.base import BaseCommand

from src.application.usecases.images import reprocess_kelvin_images


class Command(BaseCommand):
    help = "Reprocess all images linked to a FujifilmExif with white_balance='Kelvin'."

    def handle(self, *args, **options):
        total, skipped = reprocess_kelvin_images.reprocess_kelvin_images()

        for path in skipped:
            self.stderr.write(f"Skipped {path} (no film simulation)")

        self.stdout.write(self.style.SUCCESS(f"Successfully reprocessed {total} images."))
