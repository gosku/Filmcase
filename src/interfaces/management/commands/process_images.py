from django.conf import settings
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from src.application.usecases.images import process_images


class Command(BaseCommand):
    help = "Import images from a folder. Enqueues Celery tasks (full stack) or processes sequentially (lite install)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("folder", type=str, help="Path to the folder containing images.")

    def handle(self, *args: object, **options: Any) -> None:
        folder = options["folder"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        summary = process_images.import_images_from_folder(folder=folder)

        if settings.USE_ASYNC_TASKS:
            self.stdout.write(self.style.SUCCESS(f"Successfully enqueued {summary.total} tasks."))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Successfully processed {summary.processed} of {summary.total} images."
        ))
        if summary.skipped:
            self.stdout.write(f"Skipped {len(summary.skipped)} image(s) that cannot produce a recipe.")
            # The full list is behind -v 2 so a large skip run does not swamp the output.
            if options["verbosity"] >= 2:
                for path in summary.skipped:
                    self.stdout.write(f"  skipped: {path}")
