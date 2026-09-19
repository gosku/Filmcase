from django.conf import settings

from src.application.usecases.library.sync_folder import resume_folder_scan
from src.application.usecases.library.sync_library import CeleryWorkerUnavailable as CeleryWorkerUnavailable
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import background, workertasks

_SYNC_FOLDER_SCAN_TASK = "src.interfaces.tasks.sync_folder_scan_task"


def trigger_folder_sync(*, folder_id: int) -> None:
    """
    Trigger a sync of a single folder from a web request.

    Starts the run in the request, which is a single fast insert: it claims the
    one-active-run-per-folder guard and gives the Library page a run to poll
    immediately. The walk of the tree, which is the slow part, then happens off
    the request: enqueued to the worker in async mode, or run in a background
    thread in sync mode.

    Returns quietly if the folder is gone or already has an active run. In async
    mode the worker is checked before the run is created, so no run is left
    stranded when nothing can process it.

    :raises CeleryWorkerUnavailable: If USE_ASYNC_TASKS is True and no Celery
        worker responds; no run is created in that case.
    """
    try:
        folder = library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        return

    if settings.USE_ASYNC_TASKS and not workertasks.is_celery_worker_available():
        raise CeleryWorkerUnavailable()

    try:
        run = library_operations.start_sync_run(folder=folder)
    except library_operations.SyncAlreadyInProgress:
        return

    if settings.USE_ASYNC_TASKS:
        workertasks.enqueue_task(
            task_name=_SYNC_FOLDER_SCAN_TASK,
            kwargs={"sync_run_id": run.pk},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
    else:
        background.run_in_background(resume_folder_scan, sync_run_id=run.pk)
