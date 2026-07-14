from collections.abc import Sequence

import attrs

from src.domain.images import operations as image_operations


@attrs.frozen
class InvalidRatingError(Exception):
    """
    Raised when the requested rating is outside the allowed range.
    """

    rating: int


@attrs.frozen
class SetImagesRatingResult:
    rated_count: int
    requested_count: int

    @property
    def not_found_count(self) -> int:
        return self.requested_count - self.rated_count


def set_images_rating(*, image_ids: Sequence[int], rating: int) -> SetImagesRatingResult:
    """
    Set *rating* on every image in *image_ids*.

    Raises:
        InvalidRatingError: If *rating* is outside the allowed range.
    """
    try:
        rated_count = image_operations.set_images_rating(image_ids=image_ids, rating=rating)
    except image_operations.InvalidImageRatingError as exc:
        raise InvalidRatingError(rating=exc.rating) from exc
    return SetImagesRatingResult(rated_count=rated_count, requested_count=len(image_ids))
