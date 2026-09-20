from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.library.sync_library_folder import (
    CeleryWorkerUnavailable,
    LibraryFolderNotFound,
    sync_library_folder,
)
from src.domain.library.queries import LibraryFolderNotFound as DomainLibraryFolderNotFound

MODULE = "src.application.usecases.library.sync_library_folder"


class TestSyncLibraryFolder:
    def test_triggers_a_sync_when_the_folder_exists(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=MagicMock()),
            patch(f"{MODULE}.trigger_folder_sync_uc.trigger_folder_sync") as mock_trigger,
        ):
            sync_library_folder(folder_id=7)

        mock_trigger.assert_called_once_with(folder_id=7)

    def test_raises_not_found_and_triggers_nothing_when_the_folder_is_gone(self):
        with (
            patch(
                f"{MODULE}.library_queries.get_library_folder",
                side_effect=DomainLibraryFolderNotFound(folder_id=7),
            ),
            patch(f"{MODULE}.trigger_folder_sync_uc.trigger_folder_sync") as mock_trigger,
        ):
            with pytest.raises(LibraryFolderNotFound):
                sync_library_folder(folder_id=7)

        mock_trigger.assert_not_called()

    def test_propagates_worker_unavailable_from_the_trigger(self):
        with (
            patch(f"{MODULE}.library_queries.get_library_folder", return_value=MagicMock()),
            patch(
                f"{MODULE}.trigger_folder_sync_uc.trigger_folder_sync",
                side_effect=CeleryWorkerUnavailable(),
            ),
        ):
            with pytest.raises(CeleryWorkerUnavailable):
                sync_library_folder(folder_id=7)
