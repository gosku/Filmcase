from django.conf import settings

from src.domain.images import events, operations, queries
from src.services import workertasks


def enqueue_images_in_folder(*, folder: str) -> int:
    """Enqueue a Celery task for every JPG image found under *folder*.

    Returns the total number of tasks enqueued.
    """
    paths = queries.collect_image_paths(folder=folder)
    for path in paths:
        workertasks.enqueue_task(
            task_name="src.interfaces.tasks.process_image_task",
            kwargs={"image_path": path},
            queue=settings.PROCESS_IMAGE_QUEUE,
        )
        events.publish_event(event_type=events.TASK_IMAGE_ENQUEUED, image_path=path)
    return len(paths)


def process_images_in_folder(*, folder: str) -> tuple[int, list[str]]:
    """Process all JPG images in *folder*, skipping those without Fujifilm metadata.

    Returns:
        A tuple of (total_found, skipped_paths).
    """
    paths = queries.collect_image_paths(folder=folder)
    skipped = []
    for path in paths:
        try:
            operations.process_image(image_path=path)
        except operations.NoFilmSimulationError:
            skipped.append(path)
    return len(paths), skipped
