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
