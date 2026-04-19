from django.conf import settings

from src.domain.images import events, operations, queries
from src.services import workertasks


class InvalidFolderError(Exception):
    """Raised when the supplied folder path is not a valid directory."""


def import_images_from_folder(*, folder: str) -> int:
    """Process all JPG images in *folder*, dispatching async or sync based on settings.

    Returns the total number of images found.

    Raises:
        InvalidFolderError: If *folder* does not exist or is not a directory.
    """
    if settings.USE_ASYNC_TASKS:
        return _enqueue_images_in_folder(folder=folder)
    total, _ = _process_images_in_folder(folder=folder)
    return total


def _enqueue_images_in_folder(*, folder: str) -> int:
    """Enqueue a Celery task for every JPG image found under *folder*.

    Returns the total number of tasks enqueued.

    Raises:
        InvalidFolderError: If *folder* does not exist or is not a directory.
    """
    try:
        paths = queries.collect_image_paths(folder=folder)
    except FileNotFoundError as exc:
        raise InvalidFolderError(folder) from exc
    for path in paths:
        workertasks.enqueue_task(
            task_name="src.interfaces.tasks.process_image_task",
            kwargs={"image_path": path},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
        events.publish_event(event_type=events.TASK_IMAGE_ENQUEUED, image_path=path)
    return len(paths)


def _process_images_in_folder(*, folder: str) -> tuple[int, list[str]]:
    """Process all JPG images in *folder* sequentially, skipping those without Fujifilm metadata.

    Returns:
        A tuple of (total_found, skipped_paths).

    Raises:
        InvalidFolderError: If *folder* does not exist or is not a directory.
    """
    try:
        paths = queries.collect_image_paths(folder=folder)
    except FileNotFoundError as exc:
        raise InvalidFolderError(folder) from exc
    skipped = []
    for path in paths:
        try:
            operations.process_image(image_path=path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped
