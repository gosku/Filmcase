from pathlib import Path

from celery import shared_task
from django.conf import settings

from src.domain.images import events, operations
from src.domain.images.thumbnails import operations as thumbnail_operations


@shared_task(name="domain.process_image", bind=True, queue=settings.PROCESS_IMAGE_QUEUE)
def process_image_task(self, *, image_path: str, **kwargs) -> str:
    """Celery task that processes a single image and stores its recipe in DB."""
    events.publish_event(
        event_type=events.TASK_IMAGE_STARTED,
        params={"image_path": image_path, "task_id": self.request.id},
    )
    try:
        recipe = operations.process_image(image_path=image_path)
    except operations.NoFilmSimulationError:
        return f"Skipped {image_path} (no film simulation)"
    events.publish_event(
        event_type=events.TASK_IMAGE_COMPLETED,
        params={"image_path": image_path, "task_id": self.request.id, "image_id": recipe.pk},
    )
    return f"Processed {recipe.filename}"


@shared_task(name="domain.generate_thumbnail", bind=True)
def generate_thumbnail_task(self, *, filepath: str, width: int, **kwargs) -> str:
    """Celery task that generates a thumbnail for a single image file."""
    thumbnail_operations.generate_thumbnail(original_path=Path(filepath), width=width)
    return f"Generated thumbnail for {Path(filepath).name}"
