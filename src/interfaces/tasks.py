from celery import shared_task

from src.domain import events, operations


@shared_task(name="domain.process_image", bind=True)
def process_image_task(self, image_path: str) -> str:
    """Celery task that processes a single image and stores its recipe in DB."""
    events.publish_event(
        event_type=events.TASK_IMAGE_STARTED,
        params={"image_path": image_path, "task_id": self.request.id},
    )
    try:
        recipe = operations.process_image(image_path)
    except operations.NoFilmSimulationError:
        return f"Skipped {image_path} (no film simulation)"
    events.publish_event(
        event_type=events.TASK_IMAGE_COMPLETED,
        params={"image_path": image_path, "task_id": self.request.id, "recipe_id": recipe.pk},
    )
    return f"Processed {recipe.filename}"
