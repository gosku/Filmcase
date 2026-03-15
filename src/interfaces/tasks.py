from celery import shared_task
from django.conf import settings

from src.domain import events, operations


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
