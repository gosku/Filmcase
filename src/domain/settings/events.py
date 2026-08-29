import structlog

logger = structlog.get_logger("settings.events")


# Event type constants (reverse domain name notation)
APP_SETTINGS_UPDATED = "settings.app.updated"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """
    Publish a structured settings event.
    """
    logger.info(event_type, event_type=event_type, **kwargs)
