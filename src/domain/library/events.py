import structlog

logger = structlog.get_logger("library.events")


# Event type constants (reverse domain name notation)
LIBRARY_FOLDER_ADDED = "library.folder.added"
LIBRARY_FOLDER_REMOVED = "library.folder.removed"
LIBRARY_FOLDER_PATH_UPDATED = "library.folder.path.updated"
LIBRARY_FOLDER_IMAGES_REMOVED = "library.folder.images.removed"
LIBRARY_IMAGE_IGNORED = "library.image.ignored"
LIBRARY_IMAGE_IGNORE_REMOVED = "library.image.ignore.removed"
LIBRARY_IMAGE_IGNORES_CLEARED = "library.image.ignores.cleared"
LIBRARY_SYNC_RUN_STARTED = "library.sync.run.started"
LIBRARY_SYNC_RUN_COMPLETED = "library.sync.run.completed"
LIBRARY_SYNC_RUN_FAILED = "library.sync.run.failed"
LIBRARY_SYNC_RUN_INTERRUPTED = "library.sync.run.interrupted"
LIBRARY_SYNC_PRUNE_STARTED = "library.sync.prune.started"
LIBRARY_SYNC_PRUNE_COMPLETED = "library.sync.prune.completed"
LIBRARY_SYNC_PRUNE_SKIPPED = "library.sync.prune.skipped"
LIBRARY_UNCOVERED_IMAGES_REMOVED = "library.images.uncovered.removed"
LIBRARY_UNCOVERED_IMAGES_SKIPPED = "library.images.uncovered.skipped"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """
    Publish a structured library event.
    """
    logger.info(event_type, event_type=event_type, **kwargs)
