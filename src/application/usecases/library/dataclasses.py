from datetime import datetime

import attrs


@attrs.frozen
class LibraryFolderData:
    folder_id: int
    path: str
    created_at: datetime
    last_processed_at: datetime | None
    last_checked_at: datetime | None


@attrs.frozen
class SyncRunData:
    folder_id: int
    total: int | None
    processed: int
    skipped: int
    errors: int
    handled: int
    percent: int
    is_active: bool
    is_scanning: bool
    is_processing: bool
    is_completed: bool
    is_failed: bool
    is_interrupted: bool


@attrs.frozen
class FilesystemEntry:
    name: str
    path: str


@attrs.frozen
class FilesystemBrowseResult:
    current_path: str
    parent_path: str | None
    entries: tuple[FilesystemEntry, ...]
