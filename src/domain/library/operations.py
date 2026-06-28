import attrs
from pathlib import Path

from django.db import IntegrityError

from src.data import models
from src.domain.library import events
from src.domain.library.queries import FolderNotFound, LibraryFolderNotFound


@attrs.frozen
class FolderAlreadyInLibrary(Exception):
    """
    Raised when a folder path is already registered in the library.
    """

    path: str


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
        folder.set_path(path=normalized)
    except IntegrityError:
        raise FolderAlreadyInLibrary(path=normalized)

    events.publish_event(
        event_type=events.LIBRARY_FOLDER_PATH_UPDATED,
        folder_id=folder.pk,
        path=folder.path,
    )
    return folder
