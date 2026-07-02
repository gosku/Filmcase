import structlog

logger = structlog.get_logger("library.events")


# Event type constants (reverse domain name notation)
LIBRARY_FOLDER_ADDED = "library.folder.added"
LIBRARY_FOLDER_REMOVED = "library.folder.removed"
LIBRARY_FOLDER_PATH_UPDATED = "library.folder.path.updated"
LIBRARY_SYNC_RUN_STARTED = "library.sync.run.started"
LIBRARY_SYNC_RUN_COMPLETED = "library.sync.run.completed"
LIBRARY_SYNC_RUN_FAILED = "library.sync.run.failed"
LIBRARY_SYNC_RUN_INTERRUPTED = "library.sync.run.interrupted"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """
    Publish a structured library event.
    """
    logger.info(event_type, event_type=event_type, **kwargs)
