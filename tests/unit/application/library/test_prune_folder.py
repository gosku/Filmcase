from unittest.mock import patch

import pytest

from src.application.usecases.library.prune_folder import LibraryFolderNotFound, prune_folder
from src.data import models
from src.domain.library import queries as library_queries

_GET_FOLDER = "src.application.usecases.library.prune_folder.library_queries.get_library_folder"
_PRUNE = "src.application.usecases.library.prune_folder.library_operations.prune_missing_images"
_UNCOVER = (
    "src.application.usecases.library.prune_folder.library_operations."
    "remove_images_no_longer_covered"
)


class TestPruneFolder:
    def test_translates_a_missing_folder_into_an_application_error(self):
        with patch(
            _GET_FOLDER,
            side_effect=library_queries.LibraryFolderNotFound(folder_id=7),
        ):
            with pytest.raises(LibraryFolderNotFound) as exc_info:
                prune_folder(folder_id=7, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert exc_info.value.folder_id == 7

    def test_removes_nothing_when_the_folder_is_missing(self):
        with (
            patch(
                _GET_FOLDER,
                side_effect=library_queries.LibraryFolderNotFound(folder_id=7),
            ),
            patch(_PRUNE) as mock_prune,
            patch(_UNCOVER) as mock_uncover,
        ):
            with pytest.raises(LibraryFolderNotFound):
                prune_folder(folder_id=7, mode=models.SyncRun.PRUNE_MODE_AUTO)

        mock_prune.assert_not_called()
        mock_uncover.assert_not_called()
