import pytest

from src.data import models
from src.domain.library import events
from src.domain.library.operations import prune_missing_images
from tests.factories import ImageFactory, LibraryFolderFactory


def _photo(*, folder, name="DSCF0001.JPG"):
    """Create a real JPEG under *folder* and a catalog record pointing at it."""
    path = folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xd8")
    return ImageFactory(filepath=str(path), filename=name), path


@pytest.fixture(autouse=True)
def _generous_guard(settings):
    # Most cases here are deliberately small; the guard has its own tests.
    settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1000


@pytest.mark.django_db
class TestPruneMissingImages:
    def test_removes_the_record_of_a_deleted_file(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image, path = _photo(folder=tmp_path)
        path.unlink()

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.removed == 1
        assert result.missing_found == 1
        assert result.skipped_reason == ""
        assert not models.Image.objects.filter(pk=image.pk).exists()

    def test_keeps_records_whose_files_are_present(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image, _ = _photo(folder=tmp_path)

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.removed == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_never_touches_images_outside_the_folder(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path / "library"))
        (tmp_path / "library").mkdir()
        outsider = ImageFactory(filepath=str(tmp_path / "elsewhere" / "DSCF9999.JPG"))

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.missing_found == 0
        assert models.Image.objects.filter(pk=outsider.pk).exists()

    def test_removes_nothing_when_the_folder_is_not_on_disk(self, tmp_path):
        missing_root = tmp_path / "unplugged"
        folder = LibraryFolderFactory(path=str(missing_root))
        image = ImageFactory(filepath=str(missing_root / "DSCF0001.JPG"))

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.skipped_reason == models.SyncRun.SKIPPED_FOLDER_MISSING
        assert result.removed == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_removes_nothing_when_pruning_is_off(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image, path = _photo(folder=tmp_path)
        path.unlink()

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_OFF)

        assert result.skipped_reason == models.SyncRun.SKIPPED_OFF
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_reports_without_removing_on_a_dry_run(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        image, path = _photo(folder=tmp_path)
        path.unlink()

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_DRY_RUN)

        assert result.skipped_reason == models.SyncRun.SKIPPED_DRY_RUN
        assert result.missing_found == 1
        assert result.removed == 0
        assert result.sample_paths == (str(path),)
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_keeps_a_record_whose_extension_the_walk_ignores(self, tmp_path):
        # The walk only matches JPEGs, so a PNG record is absent from its result.
        # Only the stat confirms whether the file is really gone.
        folder = LibraryFolderFactory(path=str(tmp_path))
        png = tmp_path / "screenshot.png"
        png.write_bytes(b"\x89PNG")
        image = ImageFactory(filepath=str(png), filename="screenshot.png")

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.missing_found == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_keeps_a_record_pointing_at_a_broken_symlink(self, tmp_path):
        # Something still occupies the path, so the conservative reading wins.
        folder = LibraryFolderFactory(path=str(tmp_path))
        link = tmp_path / "DSCF0001.JPG"
        link.symlink_to(tmp_path / "nowhere.JPG")
        image = ImageFactory(filepath=str(link), filename="DSCF0001.JPG")

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.missing_found == 0
        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_publishes_prune_completed(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        _, path = _photo(folder=tmp_path)
        path.unlink()

        prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_PRUNE_COMPLETED]
        assert len(matching) == 1
        assert matching[0]["folder_id"] == folder.pk
        assert matching[0]["removed"] == 1


@pytest.mark.django_db
class TestPruneMissingImagesSafetyGuard:
    @pytest.fixture(autouse=True)
    def _strict_guard(self, settings):
        settings.LIBRARY_PRUNE_GUARD_FRACTION = 0.5
        settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 2

    def test_removes_nothing_when_the_guard_trips(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        for index in range(4):
            _, path = _photo(folder=tmp_path, name=f"DSCF000{index}.JPG")
            path.unlink()

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        assert result.skipped_reason == models.SyncRun.SKIPPED_GUARD
        assert result.missing_found == 4
        assert result.removed == 0
        assert models.Image.objects.count() == 4

    def test_forcing_the_prune_overrides_the_guard(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        for index in range(4):
            _, path = _photo(folder=tmp_path, name=f"DSCF000{index}.JPG")
            path.unlink()

        result = prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_FORCE)

        assert result.skipped_reason == ""
        assert result.removed == 4
        assert models.Image.objects.count() == 0

    def test_publishes_prune_skipped_when_the_guard_trips(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        for index in range(4):
            _, path = _photo(folder=tmp_path, name=f"DSCF000{index}.JPG")
            path.unlink()

        prune_missing_images(folder=folder, mode=models.SyncRun.PRUNE_MODE_AUTO)

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_SYNC_PRUNE_SKIPPED]
        assert len(matching) == 1
        assert matching[0]["reason"] == models.SyncRun.SKIPPED_GUARD
        assert matching[0]["missing_found"] == 4
        assert matching[0]["total"] == 4
