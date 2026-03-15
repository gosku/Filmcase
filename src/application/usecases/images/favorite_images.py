from src.data.models import Image
from src.domain.images import operations, queries


def mark_image_as_favorite(*, image_path: str) -> Image:
    """Find or process the Image for *image_path* and mark it as a favourite.

    If the image is not yet in the database, or the match is ambiguous,
    it is first processed and stored via process_image().

    Raises:
        operations.NoFilmSimulationError: If the image has no Fujifilm metadata.
    """
    try:
        image = queries.find_image_for_path(image_path=image_path)
    except (queries.ImageNotFound, queries.AmbiguousImageMatch):
        image = operations.process_image(image_path=image_path)
    image.set_as_favorite()
    return image
