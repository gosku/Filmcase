from pathlib import Path

import attrs

from src.data.models import Image
from src.domain.images.thumbnails.queries import thumbnail_cache_path
from src.interfaces.tasks import generate_thumbnail_task


@attrs.frozen
class ThumbnailGenerationResult:
    enqueued: int
    already_cached: int
    missing_paths: list[str]


def generate_thumbnails_for_all_images(*, width: int) -> ThumbnailGenerationResult:
    """Enqueue a thumbnail-generation task for every image in the database.

    Images whose source file is missing on disk are skipped and reported.
    Images that already have a cached thumbnail are skipped silently.

    Returns a :class:`ThumbnailGenerationResult` with the number of tasks
    enqueued, thumbnails that were already cached, and paths that are missing.
    """
    enqueued = already_cached = 0
    missing_paths: list[str] = []

    for image in Image.objects.only("filepath").iterator():
        path = Path(image.filepath)
        if not path.is_file():
            missing_paths.append(image.filepath)
            continue
        if thumbnail_cache_path(original_path=path, width=width).is_file():
            already_cached += 1
            continue
        generate_thumbnail_task.apply_async(kwargs={"filepath": image.filepath, "width": width})
        enqueued += 1

    return ThumbnailGenerationResult(
        enqueued=enqueued,
        already_cached=already_cached,
        missing_paths=missing_paths,
    )
