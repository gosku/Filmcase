import structlog

logger = structlog.get_logger("events")


# Event type constants (reverse domain name notation)
RECIPE_CREATED = "recipe.created"
RECIPE_DEDUPLICATED = "recipe.deduplicated"
RECIPE_IMAGE_CREATED = "recipe.image.created"
RECIPE_IMAGE_UPDATED = "recipe.image.updated"
RECIPE_COVER_IMAGE_SET = "recipe.cover.image.set"
RECIPE_CARD_CREATED = "recipe.card.created"
RECIPE_CARD_REMOVED = "recipe.card.removed"
RECIPE_REMOVED = "recipe.removed"
RECIPE_UPDATED = "recipe.updated"
RECIPE_ADDED_TO_VERSION_LINE = "recipe.version_line.added"
RECIPE_IMPORT_QR_CARD_FAILED = "recipe.import.qr_card.failed"
IMAGE_RATING_SET = "image.rating.set"
IMAGE_RATING_FAILED = "image.rating.failed"
TASK_IMAGE_ENQUEUED = "task.image.enqueued"
TASK_IMAGE_STARTED = "task.image.started"
TASK_IMAGE_COMPLETED = "task.image.completed"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """
    Publish a structured application event.
    """
    logger.info(event_type, event_type=event_type, **kwargs)
