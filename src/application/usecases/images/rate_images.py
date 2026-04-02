import attrs

from src.domain.images import events, operations, queries


@attrs.frozen
class RateFolderResult:
    rated: tuple[str, ...]
    skipped: tuple[str, ...]


def rate_images_in_folder(*, folder: str, rating: int) -> RateFolderResult:
    """Rate every Fujifilm image found under *folder* with *rating*.

    Returns a result describing which files were rated and which were
    skipped. An IMAGE_RATING_FAILED event is published for each image
    that cannot be rated.
    """
    paths = queries.collect_image_paths(folder=folder)
    rated: list[str] = []
    skipped: list[str] = []
    for path in paths:
        try:
            operations.rate_image(image_path=path, rating=rating)
            rated.append(path)
        except operations.UnableToRateImage:
            events.publish_event(event_type=events.IMAGE_RATING_FAILED, image_path=path)
            skipped.append(path)
    return RateFolderResult(rated=tuple(rated), skipped=tuple(skipped))
