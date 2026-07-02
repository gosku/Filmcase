from django.db import models
from django.utils import timezone

from ._library import LibraryFolder

_STATE_SCANNING = "SCANNING"
_STATE_PROCESSING = "PROCESSING"
_STATE_COMPLETED = "COMPLETED"
_STATE_FAILED = "FAILED"
_STATE_INTERRUPTED = "INTERRUPTED"

# A run is "active" while it is scanning or processing; at most one active run is
# allowed per folder (enforced by a conditional UniqueConstraint below).
_ACTIVE_STATES = (_STATE_SCANNING, _STATE_PROCESSING)

_STATE_MAX_LEN = 16


class SyncRun(models.Model):
    STATE_SCANNING = _STATE_SCANNING
    STATE_PROCESSING = _STATE_PROCESSING
    STATE_COMPLETED = _STATE_COMPLETED
    STATE_FAILED = _STATE_FAILED
    STATE_INTERRUPTED = _STATE_INTERRUPTED
    ACTIVE_STATES = _ACTIVE_STATES

    folder = models.ForeignKey(
        LibraryFolder,
        on_delete=models.CASCADE,
        related_name="sync_runs",
    )
    state = models.CharField(max_length=_STATE_MAX_LEN)
    total = models.IntegerField(null=True)  # unknown during the scanning phase
    processed = models.IntegerField(default=0)
    skipped = models.IntegerField(default=0)
    errors = models.IntegerField(default=0)
    error_message = models.TextField(null=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["folder", "-started_at"], name="idx_sync_run_folder_started"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["folder"],
                condition=models.Q(state__in=_ACTIVE_STATES),
                name="unique_active_sync_run_per_folder",
            ),
        ]

    # Factories

    @classmethod
    def create(cls, *, folder: LibraryFolder) -> "SyncRun":
        return cls.objects.create(folder=folder, state=_STATE_SCANNING)

    # Mutators

    def begin_processing(self, *, total: int) -> None:
        self.state = _STATE_PROCESSING
        self.total = total
        self.save(update_fields=["state", "total", "updated_at"])

    def record_processed(self) -> None:
        self._increment("processed")

    def record_skipped(self) -> None:
        self._increment("skipped")

    def record_error(self) -> None:
        self._increment("errors")

    def _increment(self, field: str) -> None:
        # Atomic increment so concurrent Celery tasks reporting against the same
        # run never lose a count. The caller must refresh_from_db() to read the
        # updated value.
        type(self).objects.filter(pk=self.pk).update(
            updated_at=timezone.now(),
            **{field: models.F(field) + 1},
        )

    def mark_completed(self) -> bool:
        # Conditional so exactly one caller wins the finalize under concurrency.
        # Returns True if this call transitioned the run to COMPLETED.
        now = timezone.now()
        rows = type(self).objects.filter(pk=self.pk, state=_STATE_PROCESSING).update(
            state=_STATE_COMPLETED,
            finished_at=now,
            updated_at=now,
        )
        return rows > 0

    def mark_failed(self, *, message: str) -> None:
        self.state = _STATE_FAILED
        self.error_message = message
        self.finished_at = timezone.now()
        self.save(update_fields=["state", "error_message", "finished_at", "updated_at"])

    # Queries

    def all_images_accounted_for(self) -> bool:
        """
        Return True once every image in the run has a terminal outcome.
        """
        if self.total is None:
            return False
        return self.processed + self.skipped + self.errors >= self.total

    def __str__(self) -> str:
        return f"#{self.id} {self.state} folder #{self.folder_id}"
