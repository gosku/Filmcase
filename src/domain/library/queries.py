import os
from datetime import datetime
from pathlib import Path

import attrs
from django.db.models import Count, QuerySet

from src.data import models


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no LibraryFolder row matches the given folder_id.
    """

    folder_id: int


@attrs.frozen
class FolderNotFound(Exception):
    """
    Raised when a filesystem path does not exist or is not a directory.
    """

    path: str


@attrs.frozen
class SyncRunNotFound(Exception):
    """
    Raised when no SyncRun row matches the given run_id.
    """

    run_id: int


@attrs.frozen
class IgnoredImageNotFound(Exception):
    """
    Raised when no IgnoredImage row matches the given ignored_id.
    """

    ignored_id: int


@attrs.frozen
class IgnoredFingerprint:
    """
    Size and modification time of a file as it was when last examined.
    """

    file_size: int
    file_modified_at: datetime


def get_ignored_fingerprints(*, folder_id: int) -> dict[str, IgnoredFingerprint]:
    """
    Return the recorded fingerprint of every ignored file under *folder_id*,
    keyed by path.

    One query, because the sync compares this against every candidate path it
    found on disk.
    """
    rows = models.IgnoredImage.objects.filter(folder_id=folder_id).values_list(
        "filepath", "file_size", "file_modified_at"
    )
    return {
        filepath: IgnoredFingerprint(file_size=file_size, file_modified_at=file_modified_at)
        for filepath, file_size, file_modified_at in rows
    }


def get_ignored_image(*, ignored_id: int) -> models.IgnoredImage:
    """
    Return the IgnoredImage with the given id.

    :raises IgnoredImageNotFound: If no row with *ignored_id* exists.
    """
    try:
        return models.IgnoredImage.objects.get(pk=ignored_id)
    except models.IgnoredImage.DoesNotExist:
        raise IgnoredImageNotFound(ignored_id=ignored_id)


def get_ignored_images(*, folder_id: int, reason: str | None = None) -> QuerySet[models.IgnoredImage]:
    """
    Return the ignored files under *folder_id*, oldest path first, optionally
    limited to one reason.

    Returns a queryset rather than a list because the caller paginates it: these
    lists run to tens of thousands of rows.
    """
    ignored = models.IgnoredImage.objects.filter(folder_id=folder_id)
    if reason is not None:
        ignored = ignored.filter(reason=reason)
    return ignored.order_by("filepath", "id")


def count_ignored_images_by_reason(*, folder_id: int) -> dict[str, int]:
    """
    Return how many files are ignored under *folder_id*, keyed by reason.
    """
    rows = (
        models.IgnoredImage.objects.filter(folder_id=folder_id)
        .values("reason")
        .annotate(total=Count("id"))
    )
    return {row["reason"]: row["total"] for row in rows}


def get_ignored_counts_by_folder() -> dict[int, int]:
    """
    Return how many files are ignored, keyed by library folder id.

    One aggregate for the whole Library page, so listing a count per row does
    not cost a query per folder.
    """
    rows = models.IgnoredImage.objects.values("folder_id").annotate(total=Count("id"))
    return {row["folder_id"]: row["total"] for row in rows}


def get_all_library_folders() -> list[models.LibraryFolder]:
    """
    Return all registered library folders ordered by path.
    """
    return list(models.LibraryFolder.objects.order_by("path"))


def get_library_folder(*, folder_id: int) -> models.LibraryFolder:
    """
    Return the LibraryFolder with the given id.

    :raises LibraryFolderNotFound: If no row with *folder_id* exists.
    """
    try:
        return models.LibraryFolder.objects.get(pk=folder_id)
    except models.LibraryFolder.DoesNotExist:
        raise LibraryFolderNotFound(folder_id=folder_id)


def list_subdirectories(*, path: str) -> tuple[str, ...]:
    """
    Return absolute paths of immediate subdirectories at *path*, sorted
    alphabetically, excluding hidden directories (those starting with '.').

    :raises FolderNotFound: If *path* does not exist or is not a directory.
    """
    root = Path(path)
    if not root.is_dir():
        raise FolderNotFound(path=path)

    entries = sorted(
        str(entry)
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )
    return tuple(entries)


def get_latest_sync_run(*, folder_id: int) -> models.SyncRun | None:
    """
    Return the most recently started sync run for *folder_id*, or None if the
    folder has never been synced.
    """
    return (
        models.SyncRun.objects.filter(folder_id=folder_id)
        .order_by("-started_at", "-id")
        .first()
    )


def get_sync_run(*, run_id: int) -> models.SyncRun:
    """
    Return the SyncRun with the given id.

    :raises SyncRunNotFound: If no run with *run_id* exists (e.g. the folder was
        removed while a task for this run was still queued).
    """
    try:
        return models.SyncRun.objects.get(pk=run_id)
    except models.SyncRun.DoesNotExist:
        raise SyncRunNotFound(run_id=run_id)


def _folder_prefix(*, path: str) -> str:
    return path.rstrip(os.sep) + os.sep


def get_exclusively_owned_image_ids(*, folder_id: int) -> list[int]:
    """
    Return the ids of images under this folder's path that no other registered
    library folder also covers.

    Library folders may nest, so an image below ``/photos/2024`` is also below
    ``/photos``. Removing the inner folder must not take images the outer one
    still monitors, so anything covered by another registered folder is excluded.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    folder = get_library_folder(folder_id=folder_id)

    owned = models.Image.objects.filter(filepath__startswith=_folder_prefix(path=folder.path))
    for other in models.LibraryFolder.objects.exclude(pk=folder_id):
        owned = owned.exclude(filepath__startswith=_folder_prefix(path=other.path))

    return list(owned.order_by("id").values_list("id", flat=True))


def count_exclusively_owned_images(*, folder_id: int) -> int:
    """
    Return how many images would leave the gallery if this folder were removed
    together with its images.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    return len(get_exclusively_owned_image_ids(folder_id=folder_id))


def get_active_sync_run(*, folder_id: int) -> models.SyncRun | None:
    """
    Return the in-progress (scanning or processing) sync run for *folder_id*, or
    None if no run is currently active. At most one active run can exist per
    folder (enforced by a database constraint).
    """
    return (
        models.SyncRun.objects.filter(
            folder_id=folder_id,
            state__in=models.SyncRun.ACTIVE_STATES,
        )
        .order_by("-started_at", "-id")
        .first()
    )
