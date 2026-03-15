from django.core.management.base import BaseCommand

from src.data.models import Image
from src.domain.operations import NoFilmSimulationError, process_image


class Command(BaseCommand):
    help = "Reprocess all images linked to a FujifilmExif with white_balance='Kelvin'."

    def handle(self, *args, **options):
        images = Image.objects.with_kelvin_white_balance().select_related("fujifilm_exif")
        total = images.count()
        self.stdout.write(f"Found {total} images with Kelvin white balance. Reprocessing…")

        for image in images:
            try:
                process_image(image.filepath)
            except NoFilmSimulationError:
                self.stderr.write(f"Skipped {image.filepath} (no film simulation)")

        self.stdout.write(self.style.SUCCESS(f"Successfully reprocessed {total} images."))
