import structlog

logger = structlog.get_logger("camera.events")


# Event type constants (reverse domain name notation)
PTP_WRITE_FAILED = "camera.ptp_write.failed"
PTP_WRITE_SUCCEEDED = "camera.ptp_write.succeeded"
PTP_READ_FAILED = "camera.ptp_read.failed"
PTP_READ_SUCCEEDED = "camera.ptp_read.succeeded"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """Publish a structured camera event."""
    logger.info(event_type, event_type=event_type, **kwargs)
