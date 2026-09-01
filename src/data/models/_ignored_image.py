from datetime import datetime

from django.db import models
from django.utils import timezone

from ._library import LibraryFolder

# Why the sync will not import a file. A file carrying one of these is left alone
# until it changes on disk or the record is removed; none of them means the file
# was deleted or altered in any way.
_IGNORED_NO_FILM_SIMULATION = "IGNORED_NO_FILM_SIMULATION"
_IGNORED_INVALID_RECIPE_DATA = "IGNORED_INVALID_RECIPE_DATA"
_IGNORED_ERROR = "IGNORED_ERROR"
# Not an import failure: the file was imported and then removed from the gallery
# by the user, who chose to keep it out. The ignore record is what stops the next
# sync re-importing it.
_IGNORED_USER_REMOVED = "IGNORED_USER_REMOVED"

_PATH_MAX_LEN = 1024
_CODE_MAX_LEN = 32


class IgnoredImage(models.Model):
    REASON_NO_FILM_SIMULATION = _IGNORED_NO_FILM_SIMULATION
    REASON_INVALID_RECIPE_DATA = _IGNORED_INVALID_RECIPE_DATA
    REASON_ERROR = _IGNORED_ERROR
    REASON_USER_REMOVED = _IGNORED_USER_REMOVED

    folder = models.ForeignKey(
        LibraryFolder,
        on_delete=models.CASCADE,
        related_name="ignored_images",
    )
    filepath = models.CharField(max_length=_PATH_MAX_LEN)
    reason = models.CharField(max_length=_CODE_MAX_LEN)
    detail = models.TextField(blank=True, default="")
    # Size and modification time as they were when the file was last examined. A
    # file whose fingerprint still matches cannot have become importable, so the
    # sync can skip it for the cost of one stat instead of one exiftool process.
    file_size = models.BigIntegerField()
    file_modified_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["folder", "reason"], name="idx_ignored_image_folder"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["filepath"],
                name="unique_ignored_image_filepath",
            ),
        ]

    # Factories

    @classmethod
    def create(
        cls,
        *,
        folder: LibraryFolder,
        filepath: str,
        reason: str,
        detail: str,
        file_size: int,
        file_modified_at: datetime,
    ) -> "IgnoredImage":
        return cls.objects.create(
            folder=folder,
            filepath=filepath,
            reason=reason,
            detail=detail,
            file_size=file_size,
            file_modified_at=file_modified_at,
        )

    # Mutators

    def set_outcome(
        self,
        *,
        reason: str,
        detail: str,
        file_size: int,
        file_modified_at: datetime,
    ) -> None:
        self.reason = reason
        self.detail = detail
        self.file_size = file_size
        self.file_modified_at = file_modified_at
        self.save(update_fields=["reason", "detail", "file_size", "file_modified_at", "updated_at"])

    def __str__(self) -> str:
        return f"#{self.id} {self.reason} {self.filepath}"
