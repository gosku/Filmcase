import attrs

from django.conf import settings

from src.application.usecases.library.sync_folder import sync_folder
from src.data import models
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import workertasks


@attrs.frozen
class CeleryWorkerUnavailable(Exception):
    """
    Raised when USE_ASYNC_TASKS is True but no Celery worker is reachable.
    """


@attrs.frozen
class SyncLibraryResult:
    folders_scanned: int
    new_files_found: int
    skipped_non_fujifilm: int
    missing_folders: tuple[str, ...]


def sync_library() -> SyncLibraryResult:
    """
    Scan every registered library folder and import new images into the catalog.

    Recovers any runs abandoned by a previous process (marking them interrupted),
    then syncs each folder in turn via the single-folder use case. In async mode,
    checks for a reachable Celery worker before doing any work.

    The result aggregates per-folder outcomes from each folder's sync run: in async
    mode ``new_files_found`` counts images enqueued for processing, in sync mode it
    counts images actually imported. Folders that no longer exist on disk are
    reported in ``missing_folders``.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds within the ping timeout.
    """
    if settings.USE_ASYNC_TASKS and not workertasks.is_celery_worker_available():
        raise CeleryWorkerUnavailable()

    library_operations.interrupt_active_sync_runs()

    folders = library_queries.get_all_library_folders()
    new_files_found = 0
    skipped_non_fujifilm = 0
    missing_folders: list[str] = []

    for folder in folders:
        sync_folder(folder_id=folder.pk)
        run = library_queries.get_latest_sync_run(folder_id=folder.pk)
        if run is None:
            continue
        if run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING:
            missing_folders.append(folder.path)
        elif settings.USE_ASYNC_TASKS:
            new_files_found += run.total or 0
        else:
            new_files_found += run.processed
            skipped_non_fujifilm += run.skipped

    return SyncLibraryResult(
        folders_scanned=len(folders),
        new_files_found=new_files_found,
        skipped_non_fujifilm=skipped_non_fujifilm,
        missing_folders=tuple(missing_folders),
    )
