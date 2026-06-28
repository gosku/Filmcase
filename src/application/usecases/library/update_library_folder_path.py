import attrs

from src.domain.library import operations as domain_operations
from src.domain.library.operations import FolderAlreadyInLibrary as DomainFolderAlreadyInLibrary
from src.domain.library.queries import FolderNotFound as DomainFolderNotFound
from src.domain.library.queries import LibraryFolderNotFound as DomainLibraryFolderNotFound
from . import _dataclasses


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


@attrs.frozen
class FolderNotFound(Exception):
    """
    Raised when the given path does not exist on disk or is not a directory.
    """

    path: str


@attrs.frozen
class FolderAlreadyInLibrary(Exception):
    """
    Raised when the given path is already registered under a different folder.
    """

    path: str


def update_library_folder_path(*, folder_id: int, path: str) -> _dataclasses.LibraryFolderData:
    """
    Update the path of the library folder with *folder_id*.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    :raises FolderNotFound: If the path does not exist or is not a directory.
    :raises FolderAlreadyInLibrary: If the path is already registered.
    """
    try:
        folder = domain_operations.update_library_folder_path(folder_id=folder_id, path=path)
    except DomainLibraryFolderNotFound as exc:
        raise LibraryFolderNotFound(folder_id=exc.folder_id)
    except DomainFolderNotFound as exc:
        raise FolderNotFound(path=exc.path)
    except DomainFolderAlreadyInLibrary as exc:
        raise FolderAlreadyInLibrary(path=exc.path)

    return _dataclasses.LibraryFolderData(
        folder_id=folder.pk,
        path=folder.path,
        created_at=folder.created_at,
        last_processed_at=folder.last_processed_at,
        last_checked_at=folder.last_checked_at,
    )
