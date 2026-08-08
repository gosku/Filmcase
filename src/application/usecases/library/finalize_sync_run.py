import structlog

from src.data import models
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries

logger = structlog.get_logger("application.library.finalize_sync_run")


def finalize_sync_run(*, run: models.SyncRun) -> None:
    """
    Finish *run*: elect a single finaliser, prune the folder, then complete it.

    Called from every place that could be the last one standing, which is the
    scan when it found nothing new and each per-image task or thread as it
    finishes. ``begin_pruning`` is a conditional update, so exactly one caller
    gets past it and the prune runs once no matter how many workers arrive here
    together.

    Pruning last is what makes a move survive: by the time this runs, every file
    that moved has been re-imported and its record repointed, so it no longer
    looks missing. Failed and interrupted runs never reach this function, so a
    folder that vanished from disk never loses images.
    """
    if not library_operations.begin_pruning(run=run):
        return

    try:
        result = _prune_for_run(run=run)
        run.record_prune_result(
            missing_found=result.missing_found,
            removed=result.removed,
            skipped_reason=result.skipped_reason,
        )
    except Exception:
        logger.exception("Failed to prune missing images for sync run")
    finally:
        library_operations.complete_sync_run(run=run)


def _prune_for_run(*, run: models.SyncRun) -> library_operations.PruneResult:
    if _another_folder_is_still_importing(folder_id=run.folder_id):
        # A file moved from this folder into one still importing has not been
        # re-imported yet, so it would look deleted. Deferring only delays the
        # removal to the next sync, which is always safe; removing early is not.
        return library_operations.PruneResult(
            missing_found=0,
            removed=0,
            total=0,
            skipped_reason=models.SyncRun.SKIPPED_DEFERRED,
            sample_paths=(),
        )

    folder = library_queries.get_library_folder(folder_id=run.folder_id)
    return library_operations.prune_missing_images(folder=folder, mode=run.prune_mode)


def _another_folder_is_still_importing(*, folder_id: int) -> bool:
    """
    Return True while another folder still has images left to import.

    What a prune has to wait for is an import that might re-point a record it
    would otherwise treat as missing, so the question is whether another folder
    still has images outstanding, not merely whether its run is open. A run that
    has accounted for every image cannot re-point anything, and treating it as a
    reason to wait would make a folder with nothing to import block its
    neighbours for no gain.
    """
    for folder in library_queries.get_all_library_folders():
        if folder.pk == folder_id:
            continue
        run = library_queries.get_active_sync_run(folder_id=folder.pk)
        if run is not None and not run.all_images_accounted_for():
            return True
    return False
