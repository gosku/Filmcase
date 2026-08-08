import attrs
from pathlib import Path

from django.db import IntegrityError, transaction
from django.utils import timezone

from src.data import models
from src.domain.library import events
from src.domain.library.queries import FolderNotFound, LibraryFolderNotFound


@attrs.frozen
class FolderAlreadyInLibrary(Exception):
    """
    Raised when a folder path is already registered in the library.
    """

    path: str


@attrs.frozen
class SyncAlreadyInProgress(Exception):
    """
    Raised when a sync run is started for a folder that already has an active run.
    """

    folder_id: int


def _normalize_path(path: str) -> str:
    return str(Path(path).expanduser().resolve())


def add_library_folder(*, path: str) -> models.LibraryFolder:
    """
    Register *path* as a monitored library folder.

    Normalizes the path (expands ~ and resolves relative segments) before
    storing it.

    :raises FolderNotFound: If the normalized path does not exist on disk
        or is not a directory.
    :raises FolderAlreadyInLibrary: If the path is already registered.
    """
    normalized = _normalize_path(path)
    if not Path(normalized).is_dir():
        raise FolderNotFound(path=normalized)

    try:
        with transaction.atomic():
            folder = models.LibraryFolder.create(path=normalized)
    except IntegrityError:
        raise FolderAlreadyInLibrary(path=normalized)

    events.publish_event(event_type=events.LIBRARY_FOLDER_ADDED, folder_id=folder.pk, path=folder.path)
    return folder


def remove_library_folder(*, folder_id: int) -> None:
    """
    Remove the library folder with *folder_id* from the monitored list.

    Does not delete any images from the catalog.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        folder = models.LibraryFolder.objects.get(pk=folder_id)
    except models.LibraryFolder.DoesNotExist:
        raise LibraryFolderNotFound(folder_id=folder_id)

    path = folder.path
    folder.delete()
    events.publish_event(event_type=events.LIBRARY_FOLDER_REMOVED, folder_id=folder_id, path=path)


def update_library_folder_path(*, folder_id: int, path: str) -> models.LibraryFolder:
    """
    Update the path of the library folder with *folder_id*.

    Normalizes the new path before storing it.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    :raises FolderNotFound: If the normalized path does not exist on disk
        or is not a directory.
    :raises FolderAlreadyInLibrary: If the normalized path is already
        registered under a different folder_id.
    """
    try:
        folder = models.LibraryFolder.objects.get(pk=folder_id)
    except models.LibraryFolder.DoesNotExist:
        raise LibraryFolderNotFound(folder_id=folder_id)

    normalized = _normalize_path(path)
    if not Path(normalized).is_dir():
        raise FolderNotFound(path=normalized)

    try:
        with transaction.atomic():
            folder.set_path(path=normalized)
    except IntegrityError:
        raise FolderAlreadyInLibrary(path=normalized)

    events.publish_event(
        event_type=events.LIBRARY_FOLDER_PATH_UPDATED,
        folder_id=folder.pk,
        path=folder.path,
    )
    return folder


def start_sync_run(*, folder: models.LibraryFolder) -> models.SyncRun:
    """
    Create a new sync run for *folder* in the scanning state.

    :raises SyncAlreadyInProgress: If *folder* already has an active (scanning or
        processing) run.
    """
    try:
        with transaction.atomic():
            run = models.SyncRun.create(folder=folder)
    except IntegrityError:
        raise SyncAlreadyInProgress(folder_id=folder.pk)

    events.publish_event(
        event_type=events.LIBRARY_SYNC_RUN_STARTED,
        run_id=run.pk,
        folder_id=folder.pk,
    )
    return run


def complete_sync_run(*, run: models.SyncRun) -> bool:
    """
    Mark *run* as completed if it is still processing or pruning.

    Uses a conditional update so that, under concurrent workers, exactly one
    caller transitions the run and publishes the completion event. Returns True
    if this call completed the run.
    """
    completed = run.transition_state(
        from_states=(models.SyncRun.STATE_PROCESSING, models.SyncRun.STATE_PRUNING),
        to_state=models.SyncRun.STATE_COMPLETED,
        finished_at=timezone.now(),
    )
    if completed:
        events.publish_event(
            event_type=events.LIBRARY_SYNC_RUN_COMPLETED,
            run_id=run.pk,
            folder_id=run.folder_id,
        )
    return completed


def fail_sync_run(*, run: models.SyncRun, message: str) -> None:
    """
    Mark *run* as failed, recording *message* as the failure reason.
    """
    run.mark_failed(message=message)
    events.publish_event(
        event_type=events.LIBRARY_SYNC_RUN_FAILED,
        run_id=run.pk,
        folder_id=run.folder_id,
        reason=message,
    )


def interrupt_active_sync_runs() -> int:
    """
    Mark every active (scanning or processing) sync run as interrupted.

    Called at startup to recover runs abandoned by a killed process, so no run
    is left permanently active. Returns the number of runs interrupted.
    """
    now = timezone.now()
    count = models.SyncRun.objects.filter(
        state__in=models.SyncRun.ACTIVE_STATES,
    ).update(
        state=models.SyncRun.STATE_INTERRUPTED,
        finished_at=now,
        updated_at=now,
    )
    if count:
        events.publish_event(
            event_type=events.LIBRARY_SYNC_RUN_INTERRUPTED,
            count=count,
        )
    return count
