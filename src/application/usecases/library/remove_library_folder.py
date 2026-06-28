import attrs

from src.domain.library import operations as domain_operations
from src.domain.library.queries import LibraryFolderNotFound as DomainLibraryFolderNotFound


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


def remove_library_folder(*, folder_id: int) -> None:
    """
    Remove the library folder with *folder_id* from the monitored list.

    Does not delete any images from the catalog.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        domain_operations.remove_library_folder(folder_id=folder_id)
    except DomainLibraryFolderNotFound as exc:
        raise LibraryFolderNotFound(folder_id=exc.folder_id)
