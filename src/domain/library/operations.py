import datetime
import os
from pathlib import Path

import attrs
from django.db import IntegrityError, transaction
from django.utils import timezone

from src.data import models
from src.domain.settings import queries as settings_queries
from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.library import events, queries
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
class UncoveredResult:
    """
    Outcome of clearing up what a folder's previous path left behind.

    ``skipped_reason`` is empty when the clean-up ran; otherwise it carries the
    SyncRun.SKIPPED_* code explaining why nothing was removed.
    """

    uncovered_found: int
    removed: int
    total: int
    skipped_reason: str


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


def remove_library_folder(*, folder_id: int, delete_images: bool) -> int:
    """
    Remove the library folder with *folder_id* from the monitored list.

    When *delete_images* is true the folder's images also leave the gallery.
    Only images no other registered folder covers are removed, so removing a
    folder nested inside another one never takes images the outer folder still
    monitors. No image file is ever deleted from disk.

    Returns the number of images removed from the gallery.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        folder = models.LibraryFolder.objects.get(pk=folder_id)
    except models.LibraryFolder.DoesNotExist:
        raise LibraryFolderNotFound(folder_id=folder_id)

    path = folder.path
    removed = 0

    if delete_images:
        # Resolved before the folder row goes, because ownership is worked out
        # by comparing this folder's path against the other registered ones.
        image_ids = queries.get_exclusively_owned_image_ids(folder_id=folder_id)
        for image in models.Image.objects.filter(pk__in=image_ids):
            image_operations.remove_image(
                image=image,
                reason=image_events.REMOVE_REASON_FOLDER_REMOVED,
            )
            removed += 1

    folder.delete()
    events.publish_event(event_type=events.LIBRARY_FOLDER_REMOVED, folder_id=folder_id, path=path)

    if removed:
        events.publish_event(
            event_type=events.LIBRARY_FOLDER_IMAGES_REMOVED,
            folder_id=folder_id,
            path=path,
            removed=removed,
        )

    return removed


def record_ignored_image(
    *,
    folder: models.LibraryFolder,
    filepath: str,
    reason: str,
    detail: str,
) -> models.IgnoredImage:
    """
    Remember that *filepath* could not be imported, so later syncs leave it alone.

    Records the file's current size and modification time. A file whose
    fingerprint still matches cannot have become importable, so the next sync can
    pass over it for the cost of one stat rather than one exiftool process. A
    file the user later fixes in place changes its fingerprint and is examined
    again on its own.

    Re-recording an existing entry replaces its fingerprint. That matters: a file
    that changed, was examined again and failed again would otherwise keep its
    stale fingerprint and be re-examined on every sync from then on.

    The file itself is never touched, and no image leaves the gallery.

    :raises OSError: If *filepath* cannot be stat'ed.
    """
    stat_result = os.stat(filepath)
    file_size = stat_result.st_size
    file_modified_at = datetime.datetime.fromtimestamp(
        stat_result.st_mtime, tz=datetime.timezone.utc
    )

    existing = models.IgnoredImage.objects.filter(filepath=filepath).first()
    if existing is not None:
        existing.set_outcome(
            reason=reason,
            detail=detail,
            file_size=file_size,
            file_modified_at=file_modified_at,
        )
        ignored = existing
    else:
        ignored = models.IgnoredImage.create(
            folder=folder,
            filepath=filepath,
            reason=reason,
            detail=detail,
            file_size=file_size,
            file_modified_at=file_modified_at,
        )

    events.publish_event(
        event_type=events.LIBRARY_IMAGE_IGNORED,
        folder_id=folder.pk,
        filepath=filepath,
        reason=reason,
    )
    return ignored


def forget_ignored_image(*, ignored_id: int) -> str:
    """
    Forget one ignored file, so the next sync examines it again.

    Returns the path that was forgotten. Removes only the record: the file is
    untouched and nothing enters the gallery until a sync imports it.

    :raises IgnoredImageNotFound: If no record with *ignored_id* exists.
    """
    ignored = queries.get_ignored_image(ignored_id=ignored_id)
    filepath = ignored.filepath
    folder_id = ignored.folder_id
    ignored.delete()

    events.publish_event(
        event_type=events.LIBRARY_IMAGE_IGNORE_REMOVED,
        folder_id=folder_id,
        filepath=filepath,
    )
    return filepath


def forget_ignored_path(*, filepath: str) -> bool:
    """
    Forget *filepath* if it is currently ignored, and report whether it was.

    Called when a file that could not be imported before succeeds, so that a
    record which no longer describes reality does not linger and show an
    imported photo as ignored.

    Silent when the path was not ignored, because that is the ordinary case.
    """
    ignored = models.IgnoredImage.objects.filter(filepath=filepath).first()
    if ignored is None:
        return False

    folder_id = ignored.folder_id
    ignored.delete()
    events.publish_event(
        event_type=events.LIBRARY_IMAGE_IGNORE_REMOVED,
        folder_id=folder_id,
        filepath=filepath,
    )
    return True


def forget_ignored_images(*, folder_id: int, reason: str | None = None) -> int:
    """
    Forget every ignored file under *folder_id*, or every one with *reason*.

    Returns how many records were forgotten. The next sync examines all of them
    again, which for a large set of permanently unimportable files means one slow
    sync before they are recorded afresh.
    """
    ignored = models.IgnoredImage.objects.filter(folder_id=folder_id)
    if reason is not None:
        ignored = ignored.filter(reason=reason)

    count, _ = ignored.delete()

    if count:
        events.publish_event(
            event_type=events.LIBRARY_IMAGE_IGNORES_CLEARED,
            folder_id=folder_id,
            reason=reason or "",
            count=count,
        )
    return count


def remove_images_no_longer_covered(
    *,
    folder: models.LibraryFolder,
    mode: str,
) -> UncoveredResult:
    """
    Remove catalog entries the folder's previous path holds and no registered
    folder covers any more.

    Removes catalog entries only: no image file is ever deleted from disk.

    Narrowing a folder, or repointing it somewhere unrelated, leaves whatever sat
    outside the new path belonging to nothing. No folder's prune can see those
    images, so without this they stay in the gallery for good, even once their
    files are deleted.

    Runs after a sync rather than when the path changes, because repointing a
    folder that moved on disk relies on the sync recognising the files and
    relocating their records. By the time this runs, anything that moved has
    followed its file into the new path and is no longer a candidate.

    The previous path is cleared only when the removal actually ran, so a guarded
    or dry run is retried on the next sync rather than forgotten.
    """
    if not folder.previous_path:
        return UncoveredResult(uncovered_found=0, removed=0, total=0, skipped_reason="")

    if mode == models.SyncRun.PRUNE_MODE_OFF:
        return UncoveredResult(
            uncovered_found=0,
            removed=0,
            total=0,
            skipped_reason=models.SyncRun.SKIPPED_OFF,
        )

    image_ids = queries.get_image_ids_no_longer_covered(folder_path=folder.previous_path)
    total = len(image_queries.get_image_paths_under_folder(folder_path=folder.previous_path))

    if mode == models.SyncRun.PRUNE_MODE_AUTO and prune_guard_trips(
        missing=len(image_ids), total=total
    ):
        events.publish_event(
            event_type=events.LIBRARY_UNCOVERED_IMAGES_SKIPPED,
            folder_id=folder.pk,
            previous_path=folder.previous_path,
            uncovered_found=len(image_ids),
            total=total,
            reason=models.SyncRun.SKIPPED_GUARD,
        )
        return UncoveredResult(
            uncovered_found=len(image_ids),
            removed=0,
            total=total,
            skipped_reason=models.SyncRun.SKIPPED_GUARD,
        )

    if mode == models.SyncRun.PRUNE_MODE_DRY_RUN:
        events.publish_event(
            event_type=events.LIBRARY_UNCOVERED_IMAGES_SKIPPED,
            folder_id=folder.pk,
            previous_path=folder.previous_path,
            uncovered_found=len(image_ids),
            total=total,
            reason=models.SyncRun.SKIPPED_DRY_RUN,
        )
        return UncoveredResult(
            uncovered_found=len(image_ids),
            removed=0,
            total=total,
            skipped_reason=models.SyncRun.SKIPPED_DRY_RUN,
        )

    removed = 0
    for image in models.Image.objects.filter(pk__in=image_ids):
        image_operations.remove_image(
            image=image,
            reason=image_events.REMOVE_REASON_NO_LONGER_IN_LIBRARY,
        )
        removed += 1

    folder.clear_previous_path()

    events.publish_event(
        event_type=events.LIBRARY_UNCOVERED_IMAGES_REMOVED,
        folder_id=folder.pk,
        uncovered_found=len(image_ids),
        removed=removed,
    )
    return UncoveredResult(
        uncovered_found=len(image_ids),
        removed=removed,
        total=total,
        skipped_reason="",
    )


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
    if missing <= settings_queries.get_library_prune_guard_min_images():
        return False
    return missing / total > settings_queries.get_library_prune_guard_fraction()


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


def update_library_folder_path(*, folder_id: int, path: str) -> models.LibraryFolder:
    """
    Update the path of the library folder with *folder_id*.

    Normalizes the new path before storing it, and remembers where the folder
    pointed before, so the next sync can clear up whatever the old path holds and
    no folder covers any more.

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

    old_path = folder.path

    try:
        with transaction.atomic():
            folder.set_path(path=normalized)
    except IntegrityError:
        raise FolderAlreadyInLibrary(path=normalized)

    # Only when empty, so two changes before a sync keep the original territory:
    # /photos -> /photos/2024 -> /photos/2024/january has to remember /photos,
    # which is the widest and the one actually holding the stranded images.
    if not folder.previous_path and old_path != normalized:
        folder.set_previous_path(path=old_path)

    events.publish_event(
        event_type=events.LIBRARY_FOLDER_PATH_UPDATED,
        folder_id=folder.pk,
        path=folder.path,
    )
    return folder


def start_sync_run(
    *,
    folder: models.LibraryFolder,
    prune_mode: str = models.SyncRun.PRUNE_MODE_AUTO,
) -> models.SyncRun:
    """
    Create a new sync run for *folder* in the scanning state.

    *prune_mode* is stored on the run because the caller that finalises it may be
    a different process entirely, and cannot be told any other way.

    :raises SyncAlreadyInProgress: If *folder* already has an active (scanning,
        processing or pruning) run.
    """
    try:
        with transaction.atomic():
            run = models.SyncRun.create(folder=folder, prune_mode=prune_mode)
    except IntegrityError:
        raise SyncAlreadyInProgress(folder_id=folder.pk)

    events.publish_event(
        event_type=events.LIBRARY_SYNC_RUN_STARTED,
        run_id=run.pk,
        folder_id=folder.pk,
    )
    return run


def begin_pruning(*, run: models.SyncRun) -> bool:
    """
    Move *run* from processing into its prune phase.

    Uses a conditional update so that, under concurrent workers, exactly one
    caller wins and the prune runs once. Returns True if this call won.

    Pruning is an active state, so the folder stays locked against a second sync
    while its tree is walked: a concurrent import could otherwise re-add files
    the prune is about to remove.
    """
    started = run.transition_state(
        from_states=(models.SyncRun.STATE_PROCESSING,),
        to_state=models.SyncRun.STATE_PRUNING,
        finished_at=None,
    )
    if started:
        events.publish_event(
            event_type=events.LIBRARY_SYNC_PRUNE_STARTED,
            run_id=run.pk,
            folder_id=run.folder_id,
        )
    return started


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


def fail_sync_run(*, run: models.SyncRun, reason: str, message: str) -> None:
    """
    Mark *run* as failed, recording *reason* as the failure code and *message* as
    the human-readable detail.

    The code lets callers tell a folder that is missing from disk apart from any
    other failure, which matters because the two need very different responses:
    a missing folder is usually an unplugged drive, and nothing should be removed
    from the gallery on its account.
    """
    run.mark_failed(reason=reason, message=message)
    events.publish_event(
        event_type=events.LIBRARY_SYNC_RUN_FAILED,
        run_id=run.pk,
        folder_id=run.folder_id,
        failure_reason=reason,
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
