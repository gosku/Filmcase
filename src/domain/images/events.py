import structlog

logger = structlog.get_logger("events")


# Event type constants (reverse domain name notation)
RECIPE_IMAGE_CREATED = "recipe.image.created"
RECIPE_IMAGE_UPDATED = "recipe.image.updated"
IMAGE_RATING_SET = "image.rating.set"
IMAGE_RATING_FAILED = "image.rating.failed"
TASK_IMAGE_ENQUEUED = "task.image.enqueued"
TASK_IMAGE_STARTED = "task.image.started"
TASK_IMAGE_COMPLETED = "task.image.completed"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """Publish a structured application event."""
    logger.info(event_type, event_type=event_type, **kwargs)
