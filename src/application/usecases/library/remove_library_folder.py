import attrs

from src.domain.library import operations as domain_operations
from src.domain.library.queries import LibraryFolderNotFound as DomainLibraryFolderNotFound


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


@attrs.frozen
class RemoveLibraryFolderResult:
    images_removed: int


def remove_library_folder(*, folder_id: int, delete_images: bool) -> RemoveLibraryFolderResult:
    """
    Remove the library folder with *folder_id* from the monitored list.

    When *delete_images* is true the folder's images also leave the gallery,
    except any a second registered folder still covers. No image file is ever
    deleted from disk.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        removed = domain_operations.remove_library_folder(
            folder_id=folder_id,
            delete_images=delete_images,
        )
    except DomainLibraryFolderNotFound as exc:
        raise LibraryFolderNotFound(folder_id=exc.folder_id)

    return RemoveLibraryFolderResult(images_removed=removed)
