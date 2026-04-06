import structlog

logger = structlog.get_logger("services.events")


# Event type constants (reverse domain name notation)
TASK_ENQUEUED = "task.enqueued"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """Publish a structured service event."""
    logger.info(event_type, event_type=event_type, **kwargs)
