import pytest

from src.application.usecases.library.remove_library_folder import (
    LibraryFolderNotFound,
    remove_library_folder,
)
from src.data import models
from tests.factories import LibraryFolderFactory


@pytest.mark.django_db
class TestRemoveLibraryFolder:
    def test_deletes_folder_from_db(self):
        folder = LibraryFolderFactory()
        remove_library_folder(folder_id=folder.pk)
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            remove_library_folder(folder_id=99999)
        assert exc_info.value.folder_id == 99999
