import structlog

logger = structlog.get_logger("camera.events")


# Event type constants (reverse domain name notation)
PTP_WRITE_FAILED = "camera.ptp_write.failed"
PTP_WRITE_SUCCEEDED = "camera.ptp_write.succeeded"
PTP_READ_FAILED = "camera.ptp_read.failed"
PTP_READ_RETRY = "camera.ptp_read.retry"
PTP_READ_SUCCEEDED = "camera.ptp_read.succeeded"

# Whole-backup transport (X-T2 and other pre-X-T3 bodies).
PTP_BACKUP_READ_SUCCEEDED = "camera.ptp_backup_read.succeeded"
PTP_BACKUP_READ_FAILED = "camera.ptp_backup_read.failed"
PTP_BACKUP_RESTORE_SUCCEEDED = "camera.ptp_backup_restore.succeeded"
PTP_BACKUP_RESTORE_FAILED = "camera.ptp_backup_restore.failed"


def publish_event(*, event_type: str, **kwargs: object) -> None:
    """
    Publish a structured camera event.
    """
    logger.info(event_type, event_type=event_type, **kwargs)
