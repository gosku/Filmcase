import os
import attrs

from src.domain.library import queries as domain_queries
from src.domain.library.queries import FolderNotFound as DomainFolderNotFound
from . import _dataclasses


@attrs.frozen
class FolderNotFound(Exception):
    """
    Raised when the given path does not exist on disk or is not a directory.
    """

    path: str


def browse_filesystem(*, path: str) -> _dataclasses.FilesystemBrowseResult:
    """
    Return the immediate subdirectories of *path* for the filesystem browser UI.

    Defaults to the user's home directory when *path* is empty.

    :raises FolderNotFound: If *path* does not exist or is not a directory.
    """
    resolved = path or os.path.expanduser("~")

    try:
        subdirs = domain_queries.list_subdirectories(path=resolved)
    except DomainFolderNotFound as exc:
        raise FolderNotFound(path=exc.path)

    parent = str(os.path.dirname(resolved)) if resolved != os.path.dirname(resolved) else None

    return _dataclasses.FilesystemBrowseResult(
        current_path=resolved,
        parent_path=parent,
        entries=tuple(
            _dataclasses.FilesystemEntry(name=os.path.basename(d), path=d)
            for d in subdirs
        ),
    )
