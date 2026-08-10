import attrs

from django.conf import settings

from src.application.usecases.library.prune_folder import prune_folder
from src.application.usecases.library.sync_folder import sync_folder
from src.data import models
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import workertasks


# Skip reasons the user needs to hear about. A dry run and an explicit --no-prune
# are what they asked for, so neither is a warning.
_REPORTED_SKIP_REASONS = (
    models.SyncRun.SKIPPED_GUARD,
    models.SyncRun.SKIPPED_DRY_RUN,
)


@attrs.frozen
class CeleryWorkerUnavailable(Exception):
    """
    Raised when USE_ASYNC_TASKS is True but no Celery worker is reachable.
    """


@attrs.frozen
class PruneWarning:
    folder_path: str
    missing_found: int
    uncovered_found: int
    total: int
    reason: str


@attrs.frozen
class SyncLibraryResult:
    folders_scanned: int
    new_files_found: int
    skipped_non_fujifilm: int
    missing_folders: tuple[str, ...]
    images_removed: int
    images_uncovered: int
    prune_warnings: tuple[PruneWarning, ...]


def sync_library(*, prune_mode: str = models.SyncRun.PRUNE_MODE_AUTO) -> SyncLibraryResult:
    """
    Scan every registered library folder, import new images into the catalog and
    remove entries whose files have disappeared.

    Recovers any runs abandoned by a previous process (marking them interrupted),
    then syncs each folder in turn via the single-folder use case. In async mode,
    checks for a reachable Celery worker before doing any work.

    The result aggregates per-folder outcomes from each folder's sync run: in async
    mode ``new_files_found`` counts images enqueued for processing, in sync mode it
    counts images actually imported. Folders that no longer exist on disk are
    reported in ``missing_folders`` and lose no images.

    Removal removes catalog entries only; no image file is deleted from disk. In
    async mode it happens in the worker after this returns, so ``images_removed``
    is zero there, the same limitation the other counts already have.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds within the ping timeout.
    """
    if settings.USE_ASYNC_TASKS and not workertasks.is_celery_worker_available():
        raise CeleryWorkerUnavailable()

    library_operations.interrupt_active_sync_runs()

    folders = library_queries.get_all_library_folders()

    if settings.USE_ASYNC_TASKS:
        return _sync_with_worker(folders=folders, prune_mode=prune_mode)
    return _sync_inline(folders=folders, prune_mode=prune_mode)


def _sync_with_worker(
    *,
    folders: list[models.LibraryFolder],
    prune_mode: str,
) -> SyncLibraryResult:
    # Every run is started back to back and stays active while its images are
    # processed, so a folder finalising early sees the others still running and
    # defers its prune. That is what protects a file moved between two folders.
    for folder in folders:
        sync_folder(folder_id=folder.pk, prune_mode=prune_mode)

    new_files_found = 0
    missing_folders: list[str] = []

    for folder in folders:
        run = library_queries.get_latest_sync_run(folder_id=folder.pk)
        if run is None:
            continue
        if run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING:
            missing_folders.append(folder.path)
        else:
            new_files_found += run.total or 0

    return SyncLibraryResult(
        folders_scanned=len(folders),
        new_files_found=new_files_found,
        skipped_non_fujifilm=0,
        missing_folders=tuple(missing_folders),
        # Necessarily zero: in async mode every run is finished by the worker,
        # so nothing has been removed by the time this returns. The Library page
        # reports what each run removed once it has.
        images_removed=0,
        images_uncovered=0,
        prune_warnings=(),
    )


def _sync_inline(
    *,
    folders: list[models.LibraryFolder],
    prune_mode: str,
) -> SyncLibraryResult:
    # Folders are scanned one after another here, so a prune run per folder would
    # fire before the later folders had been looked at, and a file moved from the
    # first folder to the last would be removed just before being re-imported.
    # Importing everything first, then pruning, keeps such a move a move.
    new_files_found = 0
    skipped_non_fujifilm = 0
    missing_folders: list[str] = []

    for folder in folders:
        sync_folder(folder_id=folder.pk, prune_mode=models.SyncRun.PRUNE_MODE_OFF)
        run = library_queries.get_latest_sync_run(folder_id=folder.pk)
        if run is None:
            continue
        if run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING:
            missing_folders.append(folder.path)
        else:
            new_files_found += run.processed
            skipped_non_fujifilm += run.skipped

    images_removed = 0
    images_uncovered = 0
    prune_warnings: list[PruneWarning] = []

    if prune_mode != models.SyncRun.PRUNE_MODE_OFF:
        for folder in folders:
            if folder.path in missing_folders:
                continue
            result = prune_folder(folder_id=folder.pk, mode=prune_mode)
            images_removed += result.removed
            images_uncovered += result.uncovered_found
            if result.skipped_reason in _REPORTED_SKIP_REASONS:
                prune_warnings.append(
                    PruneWarning(
                        folder_path=result.folder_path,
                        missing_found=result.missing_found,
                        uncovered_found=result.uncovered_found,
                        total=result.total,
                        reason=result.skipped_reason,
                    )
                )

    return SyncLibraryResult(
        folders_scanned=len(folders),
        new_files_found=new_files_found,
        skipped_non_fujifilm=skipped_non_fujifilm,
        missing_folders=tuple(missing_folders),
        images_removed=images_removed,
        images_uncovered=images_uncovered,
        prune_warnings=tuple(prune_warnings),
    )
