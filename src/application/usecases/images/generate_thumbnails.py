from pathlib import Path

import attrs

from src.data.models import Image
from src.domain.images.thumbnails.operations import generate_thumbnail
from src.domain.images.thumbnails.queries import thumbnail_cache_path


@attrs.frozen
class ThumbnailGenerationResult:
    generated: int
    already_cached: int
    missing_paths: list[str]
    error_paths: list[str]


def generate_thumbnails_for_all_images(*, width: int) -> ThumbnailGenerationResult:
    """Generate thumbnails for every image in the database.

    Skips images whose source file is missing on disk.  Skips generation when
    a cached thumbnail already exists.  Catches per-image errors so a single
    bad file does not abort the whole run.

    Returns a :class:`ThumbnailGenerationResult` with counts and problem paths.
    """
    generated = already_cached = 0
    missing_paths: list[str] = []
    error_paths: list[str] = []

    for image in Image.objects.only("filepath").iterator():
        path = Path(image.filepath)
        if not path.is_file():
            missing_paths.append(image.filepath)
            continue
        try:
            was_cached = thumbnail_cache_path(original_path=path, width=width).is_file()
            generate_thumbnail(original_path=path, width=width)
            if was_cached:
                already_cached += 1
            else:
                generated += 1
        except Exception:
            error_paths.append(image.filepath)

    return ThumbnailGenerationResult(
        generated=generated,
        already_cached=already_cached,
        missing_paths=missing_paths,
        error_paths=error_paths,
    )
