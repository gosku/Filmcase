from django.conf import settings

from src.application.usecases.library.finalize_folder_removal import finalize_folder_removal
from src.application.usecases.library.remove_folder_image import remove_folder_image
from src.domain.library import queries as library_queries
from src.services import workertasks

_REMOVE_FOLDER_IMAGE_TASK = "src.interfaces.tasks.remove_folder_image_task"


def run_folder_removal(*, sync_run_id: int) -> None:
    """
    Orchestrate a folder removal for an already-started removal run.

    Resolves the images the folder solely owns (which must happen before the
    folder row goes, since ownership is worked out by comparing paths), records
    the count on the run so the page can show progress, then hands each image off
    to be removed: one Celery task per image in async mode, or an inline loop in
    lite mode. A folder that owns nothing is finalised straight away.

    Runs off the request (in the worker or a background thread), so dispatching
    one message per image here does not block anything. Returns quietly if the run
    or its folder is already gone.
    """
    try:
        run = library_queries.get_sync_run(run_id=sync_run_id)
    except library_queries.SyncRunNotFound:
        return

    try:
        library_queries.get_library_folder(folder_id=run.folder_id)
    except library_queries.LibraryFolderNotFound:
        return

    image_ids = library_queries.get_exclusively_owned_image_ids(folder_id=run.folder_id)
    run.set_removal_total(total=len(image_ids))

    if not image_ids:
        finalize_folder_removal(run=run)
        return

    if settings.USE_ASYNC_TASKS:
        workertasks.enqueue_tasks(
            task_name=_REMOVE_FOLDER_IMAGE_TASK,
            kwargs_list=[
                {"image_id": image_id, "sync_run_id": run.pk} for image_id in image_ids
            ],
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
        return

    for image_id in image_ids:
        remove_folder_image(image_id=image_id, sync_run_id=run.pk)
