import os
from datetime import datetime, timezone

from django.conf import settings

from src.application.usecases.library.finalize_sync_run import finalize_sync_run
from src.application.usecases.library.process_synced_image import process_synced_image
from src.data import models
from src.domain.images import queries as image_queries
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries
from src.services import workertasks

_SYNC_DISPATCH_IMAGE_BATCH_TASK = "src.interfaces.tasks.sync_dispatch_image_batch_task"
_FINALIZE_SYNC_RUN_TASK = "src.interfaces.tasks.finalize_sync_run_task"


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
    candidates = sorted(set(found_paths) - known_paths)
    new_paths = _drop_unchanged_ignored(folder_id=folder.pk, candidates=candidates)

    run.begin_processing(total=len(new_paths))
    folder.set_last_checked_at(value=now)
    if new_paths:
        folder.set_last_processed_at(value=now)

    if not new_paths:
        # Nothing new is exactly the case where photos were deleted, so this
        # branch still has to finalise (and therefore prune).
        _finalize(run=run)
        return

    _dispatch(new_paths=new_paths, run=run)


def _drop_unchanged_ignored(*, folder_id: int, candidates: list[str]) -> list[str]:
    """
    Return the candidates worth examining, dropping files already known to be
    unimportable that have not changed since they were last looked at.

    A file the sync cannot import has no catalog entry, so it would otherwise be
    rediscovered on every single sync and re-read from scratch each time. On a
    large library that is thousands of pointless exiftool processes per startup.

    The fingerprint check costs one stat, and only for candidates that already
    have a record, so the extra syscalls are bounded by how many files are
    ignored rather than by the size of the tree. Anything whose size or
    modification time has moved falls through to be examined again, which is how
    a file the user fixes in place comes back on its own.
    """
    fingerprints = library_queries.get_ignored_fingerprints(folder_id=folder_id)
    if not fingerprints:
        return candidates

    worth_examining = []
    for path in candidates:
        fingerprint = fingerprints.get(path)
        if fingerprint is None:
            worth_examining.append(path)
            continue
        try:
            stat_result = os.stat(path)
        except OSError:
            # Gone between the walk and now. The next sync will not find it either.
            continue
        modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc)
        if stat_result.st_size != fingerprint.file_size or modified_at != fingerprint.file_modified_at:
            worth_examining.append(path)

    return worth_examining


def _dispatch(*, new_paths: list[str], run: models.SyncRun) -> None:
    """
    Hand the new images to whoever will process them.

    In async mode they go to the worker in batches, and each batch is expanded
    into one message per image by the worker that picks it up. Dispatching is
    synchronous, so the command that started the sync cannot return until the last
    message is published: one message per file here would block startup for as
    long as publishing takes, which on tens of thousands of files is tens of
    seconds before the server is even reachable.

    Batching only the first level keeps that cost down without making a batch a
    unit of work, which would cap parallelism at the number of batches however
    many workers were free.
    """
    if not settings.USE_ASYNC_TASKS:
        for path in new_paths:
            process_synced_image(image_path=path, sync_run_id=run.pk)
        return

    workertasks.enqueue_tasks(
        task_name=_SYNC_DISPATCH_IMAGE_BATCH_TASK,
        kwargs_list=[
            {"image_paths": batch, "sync_run_id": run.pk}
            for batch in _batched(new_paths, settings.SYNC_IMAGE_BATCH_SIZE)
        ],
        queue=settings.PROCESS_IMAGE_QUEUE,
    )


def _finalize(*, run: models.SyncRun) -> None:
    """
    Finish a run that had no images to process.

    In async mode this goes to the worker, like every other part of a sync.
    Doing it here instead would put a second full walk of the folder, and the
    removals that follow it, inside whoever started the sync: the startup
    command before the server is reachable, or a web request. It would also mean
    the same work happened in the worker or in the caller depending only on
    whether anything happened to be new.
    """
    if not settings.USE_ASYNC_TASKS:
        finalize_sync_run(run=run)
        return

    workertasks.enqueue_task(
        task_name=_FINALIZE_SYNC_RUN_TASK,
        kwargs={"sync_run_id": run.pk},
        queue=settings.PROCESS_IMAGE_QUEUE,
    )


def _batched(paths: list[str], size: int) -> list[list[str]]:
    return [paths[start : start + size] for start in range(0, len(paths), size)]
