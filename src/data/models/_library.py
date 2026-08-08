from datetime import datetime

from django.db import models
from django.utils import timezone

_PATH_MAX_LEN = 1024


class LibraryFolder(models.Model):
    path = models.CharField(max_length=_PATH_MAX_LEN)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    last_processed_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["path"],
                name="unique_library_folder_path",
            ),
        ]

    # Factories

    @classmethod
    def create(cls, *, path: str) -> "LibraryFolder":
        return cls.objects.create(path=path)

    # Mutators

    def set_path(self, *, path: str) -> None:
        self.path = path
        self.save(update_fields=["path", "updated_at"])

    def set_last_processed_at(self, *, value: datetime) -> None:
        self.last_processed_at = value
        self.save(update_fields=["last_processed_at", "updated_at"])

    def set_last_checked_at(self, *, value: datetime) -> None:
        self.last_checked_at = value
        self.save(update_fields=["last_checked_at", "updated_at"])

    def __str__(self) -> str:
        return f"#{self.id} {self.path}"
