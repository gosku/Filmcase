from pathlib import Path

import attrs
from django.conf import settings

from src.data import models
from src.domain.images.thumbnails import queries as thumbnail_queries
from src.services import workertasks


@attrs.frozen
class ThumbnailGenerationResult:
    enqueued: int
    already_cached: int
    missing_paths: tuple[str, ...]


def generate_thumbnails_for_all_images(*, width: int) -> ThumbnailGenerationResult:
    """Enqueue a thumbnail-generation task for every image in the database.

    Images whose source file is missing on disk are skipped and reported.
    Images that already have a cached thumbnail are skipped silently.

    Returns a :class:`ThumbnailGenerationResult` with the number of tasks
    enqueued, thumbnails that were already cached, and paths that are missing.
    """
    enqueued = already_cached = 0
    missing_paths: list[str] = []

    for image in models.Image.objects.only("filepath").iterator():
        path = Path(image.filepath)
        if not path.is_file():
            missing_paths.append(image.filepath)
            continue
        if thumbnail_queries.thumbnail_cache_path(original_path=path, width=width).is_file():
            already_cached += 1
            continue
        workertasks.enqueue_task(
            task_name="src.interfaces.tasks.generate_thumbnail_task",
            kwargs={"filepath": image.filepath, "width": width},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
        enqueued += 1

    return ThumbnailGenerationResult(
        enqueued=enqueued,
        already_cached=already_cached,
        missing_paths=tuple(missing_paths),
    )
