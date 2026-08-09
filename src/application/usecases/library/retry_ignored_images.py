import attrs

from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder with the given id exists.
    """

    folder_id: int


@attrs.frozen
class IgnoredImageNotFound(Exception):
    """
    Raised when no ignored-image record with the given id exists.
    """

    ignored_id: int


@attrs.frozen
class RetryIgnoredImagesResult:
    forgotten: int


@attrs.frozen
class RetryIgnoredImageResult:
    filepath: str


def retry_ignored_images(*, folder_id: int, reason: str | None = None) -> RetryIgnoredImagesResult:
    """
    Forget what a folder has ignored, so the next sync examines those files again.

    Limiting to one reason is the common case: a batch that failed for an
    environmental reason deserves another look, while files that are simply not
    Fujifilm do not.

    Forgets records only. No file is touched, and nothing enters the gallery
    until a sync actually imports it.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        raise LibraryFolderNotFound(folder_id=folder_id)

    forgotten = library_operations.forget_ignored_images(folder_id=folder_id, reason=reason)
    return RetryIgnoredImagesResult(forgotten=forgotten)


def retry_ignored_image(*, ignored_id: int) -> RetryIgnoredImageResult:
    """
    Forget one ignored file, so the next sync examines it again.

    :raises IgnoredImageNotFound: If no record with *ignored_id* exists.
    """
    try:
        filepath = library_operations.forget_ignored_image(ignored_id=ignored_id)
    except library_queries.IgnoredImageNotFound:
        raise IgnoredImageNotFound(ignored_id=ignored_id)

    return RetryIgnoredImageResult(filepath=filepath)
