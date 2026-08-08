import attrs

from src.domain.library import queries as library_queries


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


@attrs.frozen
class FolderRemovalPreview:
    folder_id: int
    path: str
    removable_images: int


def get_folder_removal_preview(*, folder_id: int) -> FolderRemovalPreview:
    """
    Describe what removing a library folder would cost, so the user can choose
    before anything happens.

    ``removable_images`` counts only images no other registered folder covers,
    which is exactly what would leave the gallery. The image files themselves are
    never deleted.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        folder = library_queries.get_library_folder(folder_id=folder_id)
        removable = library_queries.count_exclusively_owned_images(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        raise LibraryFolderNotFound(folder_id=folder_id)

    return FolderRemovalPreview(
        folder_id=folder.pk,
        path=folder.path,
        removable_images=removable,
    )
