from src.application.usecases.library.finalize_folder_removal import finalize_folder_removal
from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.library import queries as library_queries


def remove_folder_image(*, image_id: int, sync_run_id: int) -> None:
    """
    Remove one image as part of a folder removal, and report it against the run.

    The unit of work behind a background folder removal: any free worker takes one
    image, so a slow file delays only itself. Whoever removes the last image
    finalises the run, which deletes the folder.

    Idempotent under a retry: if the run is gone the call returns, and if the image
    is already gone it is not counted again, so a redelivered message cannot push
    the run past its total or double-delete a folder.
    """
    try:
        run = library_queries.get_sync_run(run_id=sync_run_id)
    except library_queries.SyncRunNotFound:
        return

    images = image_queries.get_images_by_ids(image_ids=[image_id])
    if not images:
        return

    image_operations.remove_image(
        image=images[0],
        reason=image_events.REMOVE_REASON_FOLDER_REMOVED,
    )
    run.record_image_removed()

    run.refresh_from_db()
    if run.all_removals_accounted_for():
        finalize_folder_removal(run=run)
