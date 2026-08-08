from collections.abc import Sequence
from datetime import datetime

from django.db import models
from django.utils import timezone

from ._library import LibraryFolder

_STATE_SCANNING = "SCANNING"
_STATE_PROCESSING = "PROCESSING"
_STATE_PRUNING = "PRUNING"
_STATE_COMPLETED = "COMPLETED"
_STATE_FAILED = "FAILED"
_STATE_INTERRUPTED = "INTERRUPTED"

# A run is "active" while it is scanning, processing or pruning; at most one active run is
# allowed per folder (enforced by a conditional UniqueConstraint below). Pruning counts as
# active so a second sync cannot start while the prune is still walking the tree.
_ACTIVE_STATES = (_STATE_SCANNING, _STATE_PROCESSING, _STATE_PRUNING)

# What the caller asked the run's prune phase to do.
_PRUNE_MODE_AUTO = "PRUNE_AUTO"
_PRUNE_MODE_FORCE = "PRUNE_FORCE"
_PRUNE_MODE_DRY_RUN = "PRUNE_DRY_RUN"
_PRUNE_MODE_OFF = "PRUNE_OFF"

# Why a run's prune phase removed nothing.
_SKIPPED_GUARD = "SKIPPED_GUARD"
_SKIPPED_DRY_RUN = "SKIPPED_DRY_RUN"
_SKIPPED_OFF = "SKIPPED_OFF"
_SKIPPED_FOLDER_MISSING = "SKIPPED_FOLDER_MISSING"
_SKIPPED_DEFERRED = "SKIPPED_DEFERRED"

# Why a run failed. error_message keeps the free-text detail.
_FAILED_FOLDER_MISSING = "FAILED_FOLDER_MISSING"

_STATE_MAX_LEN = 16
_PRUNE_MODE_MAX_LEN = 16
_CODE_MAX_LEN = 32


class SyncRun(models.Model):
    STATE_SCANNING = _STATE_SCANNING
    STATE_PROCESSING = _STATE_PROCESSING
    STATE_PRUNING = _STATE_PRUNING
    STATE_COMPLETED = _STATE_COMPLETED
    STATE_FAILED = _STATE_FAILED
    STATE_INTERRUPTED = _STATE_INTERRUPTED
    ACTIVE_STATES = _ACTIVE_STATES

    PRUNE_MODE_AUTO = _PRUNE_MODE_AUTO
    PRUNE_MODE_FORCE = _PRUNE_MODE_FORCE
    PRUNE_MODE_DRY_RUN = _PRUNE_MODE_DRY_RUN
    PRUNE_MODE_OFF = _PRUNE_MODE_OFF

    SKIPPED_GUARD = _SKIPPED_GUARD
    SKIPPED_DRY_RUN = _SKIPPED_DRY_RUN
    SKIPPED_OFF = _SKIPPED_OFF
    SKIPPED_FOLDER_MISSING = _SKIPPED_FOLDER_MISSING
    SKIPPED_DEFERRED = _SKIPPED_DEFERRED

    FAILED_FOLDER_MISSING = _FAILED_FOLDER_MISSING

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
    removed = models.IntegerField(default=0)
    missing_found = models.IntegerField(default=0)
    uncovered_found = models.IntegerField(default=0)
    prune_mode = models.CharField(max_length=_PRUNE_MODE_MAX_LEN, default=_PRUNE_MODE_AUTO)
    prune_skipped = models.CharField(max_length=_CODE_MAX_LEN, blank=True, default="")
    error_message = models.TextField(null=True)
    failure_reason = models.CharField(max_length=_CODE_MAX_LEN, blank=True, default="")
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
    def create(cls, *, folder: LibraryFolder, prune_mode: str = _PRUNE_MODE_AUTO) -> "SyncRun":
        return cls.objects.create(folder=folder, state=_STATE_SCANNING, prune_mode=prune_mode)

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

    def transition_state(
        self,
        *,
        from_states: Sequence[str],
        to_state: str,
        finished_at: datetime | None,
    ) -> bool:
        """
        Move this run to *to_state* only if it is currently in one of *from_states*.

        A single conditional UPDATE, so under concurrent workers exactly one caller
        gets True. The caller decides which transitions are legal and whether the
        target state is terminal, passing finished_at=None when it is not.
        """
        rows = type(self).objects.filter(pk=self.pk, state__in=from_states).update(
            state=to_state,
            finished_at=finished_at,
            updated_at=timezone.now(),
        )
        return rows > 0

    def mark_failed(self, *, reason: str, message: str) -> None:
        self.state = _STATE_FAILED
        self.failure_reason = reason
        self.error_message = message
        self.finished_at = timezone.now()
        self.save(update_fields=["state", "failure_reason", "error_message", "finished_at", "updated_at"])

    def record_removal_results(
        self,
        *,
        missing_found: int,
        uncovered_found: int,
        removed: int,
        skipped_reason: str,
    ) -> None:
        self.missing_found = missing_found
        self.uncovered_found = uncovered_found
        self.removed = removed
        self.prune_skipped = skipped_reason
        self.save(
            update_fields=[
                "missing_found",
                "uncovered_found",
                "removed",
                "prune_skipped",
                "updated_at",
            ]
        )

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
