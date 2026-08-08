from datetime import datetime, timezone

from django.conf import settings

from src.application.usecases.library.finalize_sync_run import finalize_sync_run
from src.application.usecases.library.process_synced_image import process_synced_image
from src.data import models
from src.domain.images import queries as image_queries
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import workertasks

_SYNC_PROCESS_IMAGE_TASK = "src.interfaces.tasks.sync_process_image_task"


def sync_folder(*, folder_id: int, prune_mode: str = models.SyncRun.PRUNE_MODE_AUTO) -> None:
    """
    Scan a single library folder, import new images and remove catalog entries
    whose files have disappeared, tracking progress in a SyncRun.

    Creates a run, walks the whole folder, and dispatches each new image: in
    async mode by enqueuing a Celery task, in sync mode by processing inline.
    Whoever handles the last image finalises the run, which is also where the
    prune happens, so imports always land before anything is removed.

    Returns without doing anything if the folder no longer exists or already has
    an active run (the concurrency guard). A folder that is missing from disk
    fails its run and removes nothing, because an unplugged drive is far more
    likely than a deletion of everything at once.
    """
    try:
        folder = library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        return

    try:
        run = library_operations.start_sync_run(folder=folder, prune_mode=prune_mode)
    except library_operations.SyncAlreadyInProgress:
        return

    # last_checked_at records when the scan started, so files added during or
    # after this scan are still caught on the next run.
    now = datetime.now(tz=timezone.utc)

    try:
        found_paths = image_queries.collect_image_paths(folder=folder.path)
    except FileNotFoundError:
        folder.set_last_checked_at(value=now)
        library_operations.fail_sync_run(
            run=run,
            reason=models.SyncRun.FAILED_FOLDER_MISSING,
            message="Folder does not exist",
        )
        return

    known_paths = image_queries.get_all_known_image_paths()
    new_paths = sorted(set(found_paths) - known_paths)

    run.begin_processing(total=len(new_paths))
    folder.set_last_checked_at(value=now)
    if new_paths:
        folder.set_last_processed_at(value=now)

    if not new_paths:
        # Nothing new is exactly the case where photos were deleted, so this
        # branch still has to finalise (and therefore prune).
        finalize_sync_run(run=run)
        return

    for path in new_paths:
        if settings.USE_ASYNC_TASKS:
            workertasks.enqueue_task(
                task_name=_SYNC_PROCESS_IMAGE_TASK,
                kwargs={"image_path": path, "sync_run_id": run.pk},
                queue=settings.PROCESS_IMAGE_QUEUE,
            )
        else:
            process_synced_image(image_path=path, sync_run_id=run.pk)
