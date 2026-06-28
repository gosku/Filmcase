import attrs
from datetime import datetime, timezone

from django.conf import settings

from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images.queries import NoFilmSimulationError
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
    Scan all registered library folders and import new images into the catalog.

    Loads all known image paths in a single DB query, then walks each folder
    and processes only paths not yet in the catalog. Paths that appear in
    multiple overlapping folders are deduplicated across the entire sync run.

    In async mode, checks for a reachable Celery worker before doing any work.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds within the ping timeout.
    """
    if settings.USE_ASYNC_TASKS and not workertasks.is_celery_worker_available():
        raise CeleryWorkerUnavailable()

    known_paths = image_queries.get_all_known_image_paths()
    folders = library_queries.get_all_library_folders()

    all_found_paths: set[str] = set()
    new_files_found = 0
    skipped_non_fujifilm = 0
    missing_folders: list[str] = []
    now = datetime.now(tz=timezone.utc)

    for folder in folders:
        try:
            found_paths = image_queries.get_image_paths_in_folder(
                folder_path=folder.path,
                last_checked_at=folder.last_checked_at,
            )
        except FileNotFoundError:
            missing_folders.append(folder.path)
            folder.set_last_checked_at(value=now)
            continue

        new_in_folder = set(found_paths) - known_paths - all_found_paths
        all_found_paths |= set(found_paths)

        processed_in_folder = 0
        for path in new_in_folder:
            if settings.USE_ASYNC_TASKS:
                workertasks.enqueue_task(
                    task_name="src.interfaces.tasks.process_image_task",
                    kwargs={"image_path": path},
                    queue=settings.PROCESS_IMAGE_QUEUE,
                )
                processed_in_folder += 1
            else:
                try:
                    image_operations.process_image(image_path=path)
                    processed_in_folder += 1
                except NoFilmSimulationError:
                    skipped_non_fujifilm += 1

        new_files_found += processed_in_folder
        folder.set_last_checked_at(value=now)
        if processed_in_folder > 0:
            folder.set_last_processed_at(value=now)

    return SyncLibraryResult(
        folders_scanned=len(folders),
        new_files_found=new_files_found,
        skipped_non_fujifilm=skipped_non_fujifilm,
        missing_folders=tuple(missing_folders),
    )
