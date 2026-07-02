from django.conf import settings

from src.application.usecases.library.sync_folder import sync_folder
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable as CeleryWorkerUnavailable
from src.services import background, workertasks


def trigger_folder_sync(*, folder_id: int) -> None:
    """
    Trigger a sync of a single folder from a web request.

    Decides how to run the sync so the request returns promptly. In async mode it
    verifies a Celery worker is reachable and then runs the sync inline (which only
    enqueues per-image tasks, so it is fast). In sync mode it runs the sync in a
    background thread, so image processing does not block the request.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds; no run is created in that case.
    """
    if settings.USE_ASYNC_TASKS:
        if not workertasks.is_celery_worker_available():
            raise CeleryWorkerUnavailable()
        sync_folder(folder_id=folder_id)
    else:
        background.run_in_background(sync_folder, folder_id=folder_id)
