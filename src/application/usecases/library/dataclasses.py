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
class FilesystemEntry:
    name: str
    path: str


@attrs.frozen
class FilesystemBrowseResult:
    current_path: str
    parent_path: str | None
    entries: tuple[FilesystemEntry, ...]
