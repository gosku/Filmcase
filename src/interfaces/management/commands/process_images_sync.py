from django.core.management.base import BaseCommand

from src.application.usecases.images import process_images


class Command(BaseCommand):
    help = "Process every JPG image found in the given folder synchronously (no Celery)."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to the folder containing images.")

    def handle(self, *args, **options):
        folder = options["folder"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        total, skipped = process_images.process_images_in_folder(folder=folder)

        for path in skipped:
            self.stderr.write(f"Skipped {path} (no film simulation)")

        self.stdout.write(self.style.SUCCESS(f"Successfully processed {total} images."))
