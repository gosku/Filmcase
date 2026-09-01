from collections.abc import Sequence

import attrs

from src.data import models
from src.domain.images import events as image_events
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.library import operations as library_operations
from src.domain.library import queries as library_queries


@attrs.frozen
class RemoveImagesResult:
    removed_count: int
    ignored_count: int
    requested_count: int

    @property
    def not_found_count(self) -> int:
        return self.requested_count - self.removed_count

    @property
    def all_succeeded(self) -> bool:
        return self.not_found_count == 0


def remove_images_from_gallery(*, image_ids: Sequence[int]) -> RemoveImagesResult:
    """
    Remove every image in *image_ids* from the gallery.

    An image whose file sits under a registered library folder is also recorded
    as ignored for that folder, so the next sync leaves it alone instead of
    re-importing a file it now has no catalog entry for. An image under no folder
    is simply removed, since nothing would re-import it. No file is deleted from
    disk.

    Ids with no matching row are skipped and counted as not found. The ignore is
    recorded before the removal: a leftover ignore record for an image that
    failed to remove is harmless, whereas a removed image with no ignore record
    would be re-imported on the next sync.
    """
    images = image_queries.get_images_by_ids(image_ids=image_ids)
    removed_count = 0
    ignored_count = 0
    for image in images:
        folder = library_queries.get_owning_folder(filepath=image.filepath)
        if folder is not None:
            try:
                library_operations.record_ignored_image(
                    folder=folder,
                    filepath=image.filepath,
                    reason=models.IgnoredImage.REASON_USER_REMOVED,
                    detail="Removed from the gallery",
                )
                ignored_count += 1
            except OSError:
                # The file is already gone from disk. A missing file is never
                # re-imported, so removing it without an ignore record is safe.
                pass
        image_operations.remove_image(
            image=image,
            reason=image_events.REMOVE_REASON_USER_REMOVED,
        )
        removed_count += 1
    return RemoveImagesResult(
        removed_count=removed_count,
        ignored_count=ignored_count,
        requested_count=len(image_ids),
    )
