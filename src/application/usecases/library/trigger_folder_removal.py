import attrs
from django.conf import settings

from src.application.usecases.library import remove_library_folder as remove_library_folder_uc
from src.application.usecases.library.run_folder_removal import run_folder_removal
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable as CeleryWorkerUnavailable
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import background, workertasks

_REMOVE_FOLDER_IMAGES_TASK = "src.interfaces.tasks.remove_folder_images_task"


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


@attrs.frozen
class SyncAlreadyInProgress(Exception):
    """
    Raised when the folder already has an active run (a sync or another removal).
    """

    folder_id: int


def trigger_folder_removal(*, folder_id: int, delete_images: bool) -> None:
    """
    Remove a library folder from a web request.

    Removing without deleting images is only a folder-row delete (plus a cascade),
    so it stays synchronous. Removing with its images can be slow on a large
    folder, so it is started as a tracked removal run in the request and drained
    off it: the per-image deletions run in the worker, or a background thread in
    lite mode. As with a sync, the worker is checked before the run is created so
    none is left stranded.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    :raises SyncAlreadyInProgress: If the folder already has an active run.
    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds; no run is created in that case.
    """
    if not delete_images:
        try:
            remove_library_folder_uc.remove_library_folder(folder_id=folder_id, delete_images=False)
        except remove_library_folder_uc.LibraryFolderNotFound:
            raise LibraryFolderNotFound(folder_id=folder_id)
        return

    try:
        folder = library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        raise LibraryFolderNotFound(folder_id=folder_id)

    if settings.USE_ASYNC_TASKS and not workertasks.is_celery_worker_available():
        raise CeleryWorkerUnavailable()

    try:
        run = library_operations.start_removal_run(folder=folder)
    except library_operations.SyncAlreadyInProgress:
        raise SyncAlreadyInProgress(folder_id=folder_id)

    if settings.USE_ASYNC_TASKS:
        workertasks.enqueue_task(
            task_name=_REMOVE_FOLDER_IMAGES_TASK,
            kwargs={"sync_run_id": run.pk},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
    else:
        background.run_in_background(run_folder_removal, sync_run_id=run.pk)
