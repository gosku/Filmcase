import pytest

from src.application.usecases.library.remove_folder_image import remove_folder_image
from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory, SyncRunFactory


@pytest.mark.django_db
class TestRemoveFolderImage:
    def test_removes_the_image_and_records_it_against_the_run(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/a.jpg")
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_REMOVING, total=2)

        remove_folder_image(image_id=image.pk, sync_run_id=run.pk)

        assert not models.Image.objects.filter(pk=image.pk).exists()
        run.refresh_from_db()
        assert run.removed == 1
        # Not the last of two, so the folder stays until the other image goes.
        assert models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_finalizes_and_deletes_the_folder_on_the_last_image(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/a.jpg")
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_REMOVING, total=1)

        remove_folder_image(image_id=image.pk, sync_run_id=run.pk)

        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_does_not_count_an_image_that_is_already_gone(self):
        folder = LibraryFolderFactory(path="/photos")
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_REMOVING, total=2)

        remove_folder_image(image_id=999999, sync_run_id=run.pk)

        run.refresh_from_db()
        assert run.removed == 0

    def test_does_nothing_when_the_run_is_gone(self):
        image = ImageFactory(filepath="/photos/a.jpg")

        remove_folder_image(image_id=image.pk, sync_run_id=999999)

        assert models.Image.objects.filter(pk=image.pk).exists()
