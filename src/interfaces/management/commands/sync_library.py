from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from src.application.usecases.library import retry_ignored_images as retry_ignored_images_usecase
from src.application.usecases.library import sync_library as sync_library_usecase
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable
from src.data import models
from src.domain.library import queries as library_queries


class Command(BaseCommand):
    help = (
        "Scan all library folders, import new images into the catalog and remove entries whose"
        " files are gone. Only catalog entries are removed; image files are never deleted."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        group = parser.add_mutually_exclusive_group()
        group.add_argument(
            "--force-prune",
            action="store_true",
            help="Remove missing images even when the mass-removal safety guard would stop it.",
        )
        group.add_argument(
            "--dry-run-prune",
            action="store_true",
            help="Report which catalog entries would be removed without removing any.",
        )
        group.add_argument(
            "--no-prune",
            action="store_true",
            help="Import only; never remove catalog entries for missing files.",
        )
        parser.add_argument(
            "--retry-failed",
            action="store_true",
            help=(
                "Examine every previously skipped or failed file again, instead of leaving them"
                " alone until they change. Slow on a library with many of them."
            ),
        )

    def handle(self, *args: object, **options: Any) -> None:
        prune_mode = _prune_mode_from(options=options)

        if options["retry_failed"]:
            forgotten = _forget_every_ignored_image()
            self.stdout.write(f"Forgot {forgotten} previously skipped or failed file(s).")

        try:
            result = sync_library_usecase.sync_library(prune_mode=prune_mode)
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
            self.stdout.write(
                "  Images whose files are gone are removed by the worker once it finishes."
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Library sync complete: {result.folders_scanned} folder(s) scanned, "
                    f"{result.new_files_found} new file(s) imported, "
                    f"{result.skipped_non_fujifilm} skipped (non-Fujifilm), "
                    f"{result.images_removed} image(s) removed from the gallery."
                )
            )

        for path in result.missing_folders:
            self.stdout.write(
                self.style.WARNING(
                    f"  Missing folder (no longer on disk): {path}."
                    " Nothing was removed from the gallery."
                )
            )

        for warning in result.prune_warnings:
            self._report(warning=warning)

    def _report(self, *, warning: sync_library_usecase.PruneWarning) -> None:
        if warning.reason == models.SyncRun.SKIPPED_DRY_RUN:
            self.stdout.write(
                f"  Would remove {warning.missing_found} of {warning.total} image(s)"
                f" from the gallery for {warning.folder_path}:"
            )
            for path in warning.sample_paths:
                self.stdout.write(f"    {path}")
            return

        self.stdout.write(
            self.style.WARNING(
                f"  Skipped removing {warning.missing_found} of {warning.total} image(s)"
                f" in {warning.folder_path} (safety guard)."
                " That usually means a drive is not mounted rather than that the photos were"
                " deleted. Re-run with --force-prune to remove them anyway."
            )
        )


def _forget_every_ignored_image() -> int:
    """
    Forget what every registered folder has ignored, so the next scan looks at
    all of it again.
    """
    return sum(
        retry_ignored_images_usecase.retry_ignored_images(folder_id=folder.pk).forgotten
        for folder in library_queries.get_all_library_folders()
    )


def _prune_mode_from(*, options: dict[str, Any]) -> str:
    if options["force_prune"]:
        return models.SyncRun.PRUNE_MODE_FORCE
    if options["dry_run_prune"]:
        return models.SyncRun.PRUNE_MODE_DRY_RUN
    if options["no_prune"]:
        return models.SyncRun.PRUNE_MODE_OFF
    return models.SyncRun.PRUNE_MODE_AUTO
