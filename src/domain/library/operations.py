import os
from pathlib import Path

import attrs
from django import conf
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.data import models
from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.library import events
from src.domain.library.queries import FolderNotFound, LibraryFolderNotFound

# How many missing paths a prune reports back for a dry run, so the caller can
# show what would go without echoing an unbounded list.
_PRUNE_SAMPLE_LIMIT = 20


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


@attrs.frozen
class PruneResult:
    """
    Outcome of a prune pass over one library folder.

    ``skipped_reason`` is empty when the prune ran; otherwise it carries the
    SyncRun.SKIPPED_* code explaining why nothing was removed.
    """

    missing_found: int
    removed: int
    total: int
    skipped_reason: str
    sample_paths: tuple[str, ...]


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


def prune_guard_trips(*, missing: int, total: int) -> bool:
    """
    Return True when removing *missing* of *total* images looks like a mass wipe
    rather than a deliberate cleanup.

    Both thresholds must be exceeded, so a small folder losing all its photos and
    a large folder losing a handful are both applied without complaint. What the
    guard is there to catch is a drive that is mounted but empty, or a directory
    that has become unreadable, where nearly everything looks gone at once.
    """
    if total <= 0:
        return False
    if missing <= conf.settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES:
        return False
    return missing / total > conf.settings.LIBRARY_PRUNE_GUARD_FRACTION


def prune_missing_images(*, folder: models.LibraryFolder, mode: str) -> PruneResult:
    """
    Remove catalog entries for images under *folder* whose files are gone.

    Removes catalog entries only: no image file is ever deleted from disk.

    Only paths under this folder are considered, so images imported from outside
    the library can never be pruned. Nothing is pruned when the folder itself is
    not on disk, because an unplugged drive must not empty the gallery.

    Candidates come from the difference between the catalogued paths and the
    files found by a fresh walk, then each candidate is confirmed with a stat.
    The walk alone is not enough: it does not follow symlinked directories, it
    silently yields nothing for a directory it cannot read, and it only matches
    JPEG extensions, so anything it misses would otherwise look deleted.
    """
    if not Path(folder.path).is_dir():
        return PruneResult(
            missing_found=0,
            removed=0,
            total=0,
            skipped_reason=models.SyncRun.SKIPPED_FOLDER_MISSING,
            sample_paths=(),
        )

    if mode == models.SyncRun.PRUNE_MODE_OFF:
        return PruneResult(
            missing_found=0,
            removed=0,
            total=0,
            skipped_reason=models.SyncRun.SKIPPED_OFF,
            sample_paths=(),
        )

    known = image_queries.get_image_paths_under_folder(folder_path=folder.path)
    found = set(image_queries.collect_image_paths(folder=folder.path))

    # os.path.lexists, not exists: a broken symlink still occupies the path, and
    # for a destructive step "something is there" has to mean "keep the record".
    missing = sorted(path for path in known - found if not os.path.lexists(path))
    sample = tuple(missing[:_PRUNE_SAMPLE_LIMIT])

    if mode == models.SyncRun.PRUNE_MODE_AUTO and prune_guard_trips(
        missing=len(missing), total=len(known)
    ):
        events.publish_event(
            event_type=events.LIBRARY_SYNC_PRUNE_SKIPPED,
            folder_id=folder.pk,
            missing_found=len(missing),
            total=len(known),
            reason=models.SyncRun.SKIPPED_GUARD,
        )
        return PruneResult(
            missing_found=len(missing),
            removed=0,
            total=len(known),
            skipped_reason=models.SyncRun.SKIPPED_GUARD,
            sample_paths=sample,
        )

    if mode == models.SyncRun.PRUNE_MODE_DRY_RUN:
        events.publish_event(
            event_type=events.LIBRARY_SYNC_PRUNE_SKIPPED,
            folder_id=folder.pk,
            missing_found=len(missing),
            total=len(known),
            reason=models.SyncRun.SKIPPED_DRY_RUN,
        )
        return PruneResult(
            missing_found=len(missing),
            removed=0,
            total=len(known),
            skipped_reason=models.SyncRun.SKIPPED_DRY_RUN,
            sample_paths=sample,
        )

    removed = 0
    for image in models.Image.objects.filter(filepath__in=missing):
        image_operations.remove_image(
            image=image,
            reason=image_events.REMOVE_REASON_FILE_MISSING,
        )
        removed += 1

    events.publish_event(
        event_type=events.LIBRARY_SYNC_PRUNE_COMPLETED,
        folder_id=folder.pk,
        missing_found=len(missing),
        removed=removed,
    )
    return PruneResult(
        missing_found=len(missing),
        removed=removed,
        total=len(known),
        skipped_reason="",
        sample_paths=sample,
    )


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
