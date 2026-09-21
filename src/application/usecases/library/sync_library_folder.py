import attrs

from src.application.usecases.library import trigger_folder_sync as trigger_folder_sync_uc
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable as CeleryWorkerUnavailable
from src.domain.library import queries as library_queries


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


def sync_library_folder(*, folder_id: int) -> None:
    """
    Re-scan a single library folder on demand from a web request.

    Unlike the fire-and-forget trigger used when a folder is added or its path
    changes, this reports a missing folder to its caller, so an on-demand request
    can 404 rather than silently do nothing. The scan itself is left to
    :func:`trigger_folder_sync`, so a folder that already has an active run is a
    harmless no-op: clicking again while a sync is under way changes nothing.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds; no run is created in that case.
    """
    try:
        library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        raise LibraryFolderNotFound(folder_id=folder_id)

    trigger_folder_sync_uc.trigger_folder_sync(folder_id=folder_id)
