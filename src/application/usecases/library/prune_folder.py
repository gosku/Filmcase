import attrs

from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries


@attrs.frozen
class LibraryFolderNotFound(Exception):
    """
    Raised when no library folder matches the given folder_id.
    """

    folder_id: int


@attrs.frozen
class PruneFolderResult:
    folder_path: str
    missing_found: int
    removed: int
    total: int
    skipped_reason: str
    sample_paths: tuple[str, ...]


def prune_folder(*, folder_id: int, mode: str) -> PruneFolderResult:
    """
    Remove catalog entries for images under one library folder whose files are
    gone, without scanning for new ones.

    Removes catalog entries only: no image file is ever deleted from disk.

    :raises LibraryFolderNotFound: If no folder with *folder_id* exists.
    """
    try:
        folder = library_queries.get_library_folder(folder_id=folder_id)
    except library_queries.LibraryFolderNotFound:
        raise LibraryFolderNotFound(folder_id=folder_id)

    result = library_operations.prune_missing_images(folder=folder, mode=mode)

    # The folder's latest run is what the Library page reads, so record the
    # outcome there even though the run itself has already finished.
    run = library_queries.get_latest_sync_run(folder_id=folder_id)
    if run is not None:
        run.record_prune_result(
            missing_found=result.missing_found,
            removed=result.removed,
            skipped_reason=result.skipped_reason,
        )

    return PruneFolderResult(
        folder_path=folder.path,
        missing_found=result.missing_found,
        removed=result.removed,
        total=result.total,
        skipped_reason=result.skipped_reason,
        sample_paths=result.sample_paths,
    )
