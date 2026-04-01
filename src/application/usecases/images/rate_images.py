import attrs

from src.data import models
from src.domain.images import operations, queries


@attrs.frozen
class RateFolderResult:
    rated: tuple[str, ...]
    skipped: tuple[str, ...]


def rate_images_in_folder(*, folder: str, rating: int) -> RateFolderResult:
    """Rate every Fujifilm image found under *folder* with *rating*.

    Returns a result describing which files were rated and which were
    skipped due to missing Fujifilm metadata.
    """
    paths = queries.collect_image_paths(folder=folder)
    rated: list[str] = []
    skipped: list[str] = []
    for path in paths:
        try:
            rate_image(image_path=path, rating=rating)
            rated.append(path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
    return RateFolderResult(rated=tuple(rated), skipped=tuple(skipped))


def rate_image(*, image_path: str, rating: int) -> models.Image:
    """Find or process the Image for *image_path* and set its rating.

    If the image is not yet in the database, or the match is ambiguous,
    it is first processed and stored via process_image().

    Raises:
        operations.NoFilmSimulationError: If the image has no Fujifilm metadata.
        operations.InvalidImageRatingError: If *rating* is out of range.
    """
    try:
        image = queries.find_image_for_path(image_path=image_path)
    except (queries.ImageNotFound, queries.AmbiguousImageMatch):
        image = operations.process_image(image_path=image_path)
    operations.set_image_rating(image=image, rating=rating)
    return image
