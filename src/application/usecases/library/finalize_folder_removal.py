from src.application.usecases.library import remove_library_folder as remove_library_folder_uc
from src.data import models
from src.domain.library import operations as library_operations


def finalize_folder_removal(*, run: models.SyncRun) -> None:
    """
    Finish a removal run once its images are gone, by deleting the folder row.

    Elects a single winner via ``complete_removal_run`` so that, when several
    per-image tasks reach the last image at once, the folder is deleted exactly
    once. The folder is removed last (with ``delete_images=False``, since the
    images have already gone through the per-image tasks), which cascades this run
    away. Returns quietly if another worker already finalised, or the folder is
    already gone.
    """
    if not library_operations.complete_removal_run(run=run):
        return

    try:
        remove_library_folder_uc.remove_library_folder(folder_id=run.folder_id, delete_images=False)
    except remove_library_folder_uc.LibraryFolderNotFound:
        return
