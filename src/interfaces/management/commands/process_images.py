from django.conf import settings
from django.core.management.base import BaseCommand

from src.application.usecases.images import process_images


class Command(BaseCommand):
    help = "Import images from a folder. Enqueues Celery tasks (full stack) or processes sequentially (lite install)."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to the folder containing images.")

    def handle(self, *args, **options):
        folder = options["folder"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        total = process_images.import_images_from_folder(folder=folder)

        if settings.USE_ASYNC_TASKS:
            self.stdout.write(self.style.SUCCESS(f"Successfully enqueued {total} tasks."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully processed {total} images."))
