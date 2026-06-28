import attrs

from src.domain.library import operations as domain_operations
from src.domain.library.operations import FolderAlreadyInLibrary as DomainFolderAlreadyInLibrary
from src.domain.library.queries import FolderNotFound as DomainFolderNotFound
from . import _dataclasses


@attrs.frozen
class FolderNotFound(Exception):
    """
    Raised when the given path does not exist on disk or is not a directory.
    """

    path: str


@attrs.frozen
class FolderAlreadyInLibrary(Exception):
    """
    Raised when the given path is already registered in the library.
    """

    path: str


def add_library_folder(*, path: str) -> _dataclasses.LibraryFolderData:
    """
    Register *path* as a monitored library folder.

    :raises FolderNotFound: If the path does not exist or is not a directory.
    :raises FolderAlreadyInLibrary: If the path is already registered.
    """
    try:
        folder = domain_operations.add_library_folder(path=path)
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
