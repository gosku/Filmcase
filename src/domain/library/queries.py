import attrs
import os
from pathlib import Path

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
