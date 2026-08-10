import pytest

from src.data import models
from src.domain.library import events
from src.domain.library.operations import remove_images_no_longer_covered
from tests.factories import ImageFactory, LibraryFolderFactory


@pytest.fixture(autouse=True)
def _generous_guard(settings):
    # These sets are deliberately tiny; the guard has its own tests below.
    settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1000


@pytest.mark.django_db
class TestRemoveImagesNoLongerCovered:
    def test_removes_what_the_narrowed_folder_left_behind(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        stranded = ImageFactory(filepath="/photos/2023/a.jpg")
        kept = ImageFactory(filepath="/photos/2024/c.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO
        )

        assert result.removed == 1
        assert result.uncovered_found == 1
        assert not models.Image.objects.filter(pk=stranded.pk).exists()
        assert models.Image.objects.filter(pk=kept.pk).exists()

    def test_clears_the_previous_path_once_it_has_run(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        ImageFactory(filepath="/photos/2023/a.jpg")

        remove_images_no_longer_covered(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        folder.refresh_from_db()
        assert folder.previous_path == ""

    def test_never_deletes_the_photo_file(self, tmp_path):
        photo = tmp_path / "a.jpg"
        photo.write_bytes(b"\xff\xd8")
        folder = LibraryFolderFactory(path=str(tmp_path / "2024"), previous_path=str(tmp_path))
        ImageFactory(filepath=str(photo))

        remove_images_no_longer_covered(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert photo.exists()

    def test_keeps_images_a_second_folder_covers(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        LibraryFolderFactory(path="/photos/2023")
        shared = ImageFactory(filepath="/photos/2023/a.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO
        )

        assert result.removed == 0
        assert models.Image.objects.filter(pk=shared.pk).exists()

    def test_does_nothing_when_there_is_no_previous_path(self):
        folder = LibraryFolderFactory(path="/photos/2024")
        image = ImageFactory(filepath="/photos/2023/a.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO
        )

        assert result.uncovered_found == 0
        assert result.skipped_reason == ""
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_removes_nothing_when_pruning_is_off(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        image = ImageFactory(filepath="/photos/2023/a.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_OFF
        )

        assert result.skipped_reason == models.SyncRun.SKIPPED_OFF
        assert models.Image.objects.filter(pk=image.pk).exists()
        folder.refresh_from_db()
        assert folder.previous_path == "/photos"

    def test_reports_without_removing_on_a_dry_run(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        image = ImageFactory(filepath="/photos/2023/a.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_DRY_RUN
        )

        assert result.skipped_reason == models.SyncRun.SKIPPED_DRY_RUN
        assert result.uncovered_found == 1
        assert result.removed == 0
        assert models.Image.objects.filter(pk=image.pk).exists()
        folder.refresh_from_db()
        assert folder.previous_path == "/photos"

    def test_publishes_uncovered_images_removed(self, captured_logs):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        ImageFactory(filepath="/photos/2023/a.jpg")

        remove_images_no_longer_covered(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_UNCOVERED_IMAGES_REMOVED
        ]
        assert len(matching) == 1
        assert matching[0]["removed"] == 1


@pytest.mark.django_db
class TestUncoveredSafetyGuard:
    @pytest.fixture(autouse=True)
    def _strict_guard(self, settings):
        settings.LIBRARY_PRUNE_GUARD_FRACTION = 0.5
        settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 2

    def test_removes_nothing_when_the_guard_trips(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        for index in range(4):
            ImageFactory(filepath=f"/photos/2023/{index}.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO
        )

        assert result.skipped_reason == models.SyncRun.SKIPPED_GUARD
        assert result.uncovered_found == 4
        assert result.removed == 0
        assert models.Image.objects.count() == 4

    def test_keeps_the_previous_path_so_the_next_sync_retries(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        for index in range(4):
            ImageFactory(filepath=f"/photos/2023/{index}.jpg")

        remove_images_no_longer_covered(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        folder.refresh_from_db()
        assert folder.previous_path == "/photos"

    def test_forcing_it_overrides_the_guard(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        for index in range(4):
            ImageFactory(filepath=f"/photos/2023/{index}.jpg")

        result = remove_images_no_longer_covered(
            folder=folder, mode=models.SyncRun.PRUNE_MODE_FORCE
        )

        assert result.removed == 4
        assert models.Image.objects.count() == 0

    def test_publishes_uncovered_images_skipped(self, captured_logs):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        for index in range(4):
            ImageFactory(filepath=f"/photos/2023/{index}.jpg")

        remove_images_no_longer_covered(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_UNCOVERED_IMAGES_SKIPPED
        ]
        assert len(matching) == 1
        assert matching[0]["reason"] == models.SyncRun.SKIPPED_GUARD
