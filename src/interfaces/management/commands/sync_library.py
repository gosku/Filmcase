from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from src.application.usecases.library import sync_library as sync_library_usecase
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable


class Command(BaseCommand):
    help = "Scan all library folders and import new images into the catalog."

    def handle(self, *args: object, **options: Any) -> None:
        try:
            result = sync_library_usecase.sync_library()
        except CeleryWorkerUnavailable:
            self.stdout.write(
                self.style.WARNING(
                    "No Celery worker is reachable. Skipping library sync."
                    " Start a worker with 'make worker' and retry."
                )
            )
            return

        if settings.USE_ASYNC_TASKS:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Library sync tasks queued: {result.folders_scanned} folder(s) scanned, "
                    f"{result.new_files_found} task(s) enqueued."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Library sync complete: {result.folders_scanned} folder(s) scanned, "
                    f"{result.new_files_found} new file(s) imported, "
                    f"{result.skipped_non_fujifilm} skipped (non-Fujifilm)."
                )
            )

        for path in result.missing_folders:
            self.stdout.write(self.style.WARNING(f"  Missing folder (no longer on disk): {path}"))
