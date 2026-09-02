import os
from datetime import datetime
from pathlib import Path

import attrs
from django.db.models import Count, Q, QuerySet

from src.data import models
from src.domain.settings import queries as settings_queries


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
    alphabetically, excluding directories whose name matches a configured
    ignored prefix (see ``get_library_ignored_directory_prefixes``). This is the
    same rule the scan uses, so junk such as hidden dirs and Synology ``@eaDir``
    folders is not offered when browsing for a folder to add.

    :raises FolderNotFound: If *path* does not exist or is not a directory.
    """
    root = Path(path)
    if not root.is_dir():
        raise FolderNotFound(path=path)

    prefixes = settings_queries.get_library_ignored_directory_prefixes()
    entries = sorted(
        str(entry)
        for entry in root.iterdir()
        if entry.is_dir()
        and not settings_queries.directory_name_is_ignored(name=entry.name, prefixes=prefixes)
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

    A folder that has changed path but not yet been synced still owns whatever
    its old path holds, since nothing else does. Without that, narrowing a folder
    and then removing it would strand those images a second time, with no
    previous path left to find them by.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    folder = get_library_folder(folder_id=folder_id)

    territory = Q(filepath__startswith=_folder_prefix(path=folder.path))
    if folder.previous_path:
        territory |= Q(filepath__startswith=_folder_prefix(path=folder.previous_path))

    owned = models.Image.objects.filter(territory)
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


def get_image_ids_no_longer_covered(*, folder_path: str) -> list[int]:
    """
    Return the ids of images under *folder_path* that no registered library
    folder covers.

    Narrowing a folder, or repointing it somewhere unrelated, leaves whatever sat
    outside the new path belonging to nothing: no folder's prune can see it, so
    it would stay in the gallery for good. This finds it, scoped to the old path
    so that images imported from outside the library are never candidates.
    """
    uncovered = models.Image.objects.filter(filepath__startswith=_folder_prefix(path=folder_path))
    for folder in models.LibraryFolder.objects.all():
        uncovered = uncovered.exclude(filepath__startswith=_folder_prefix(path=folder.path))

    return list(uncovered.order_by("id").values_list("id", flat=True))


def get_owning_folder(*, filepath: str) -> models.LibraryFolder | None:
    """
    Return the registered library folder that *filepath* sits under, or None if
    no folder covers it.

    Folders may nest, so a file below ``/photos/2024`` is under both ``/photos``
    and ``/photos/2024``. The most specific one owns it, so the folder with the
    longest matching path prefix wins. Membership is purely lexical, the same
    path-prefix inference the coverage queries above use (ADR 015).
    """
    owning: models.LibraryFolder | None = None
    for folder in models.LibraryFolder.objects.all():
        if filepath.startswith(_folder_prefix(path=folder.path)):
            if owning is None or len(folder.path) > len(owning.path):
                owning = folder
    return owning


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
