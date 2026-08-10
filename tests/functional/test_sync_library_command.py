import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from src.application.usecases.library.sync_library import CeleryWorkerUnavailable
from src.data import models
from src.domain.library.operations import update_library_folder_path
from tests.factories import LibraryFolderFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"


@pytest.mark.django_db
class TestSyncLibraryCommand:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_reports_sync_complete_with_counts(self, tmp_path, capsys):
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))

        call_command("sync_library")

        captured = capsys.readouterr()
        assert "Library sync complete" in captured.out
        assert "1 folder(s) scanned" in captured.out
        assert "1 new file(s) imported" in captured.out

    @override_settings(USE_ASYNC_TASKS=False)
    def test_imports_image_into_catalog(self, tmp_path, capsys):
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))

        call_command("sync_library")

        assert models.Image.objects.filter(
            filepath=str(tmp_path / FUJIFILM_FIXTURE.name)
        ).exists()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_reports_missing_folder_warning(self, tmp_path, capsys):
        missing_path = str(tmp_path / "does_not_exist")
        LibraryFolderFactory(path=missing_path)

        call_command("sync_library")

        captured = capsys.readouterr()
        assert "Missing folder" in captured.out
        assert missing_path in captured.out

    def test_prints_warning_and_exits_when_celery_worker_unavailable(self, capsys):
        with patch(
            "src.application.usecases.library.sync_library.sync_library",
            side_effect=CeleryWorkerUnavailable(),
        ):
            call_command("sync_library")

        captured = capsys.readouterr()
        assert "No Celery worker is reachable" in captured.out


@pytest.mark.django_db
class TestSyncLibraryCommandRemovesMissingImages:
    @pytest.fixture(autouse=True)
    def _lite_mode(self, settings):
        settings.USE_ASYNC_TASKS = False

    def _library_with_a_deleted_photo(self, tmp_path):
        photo = tmp_path / FUJIFILM_FIXTURE.name
        shutil.copy(FUJIFILM_FIXTURE, photo)
        folder = LibraryFolderFactory(path=str(tmp_path))
        call_command("sync_library")
        photo.unlink()
        return folder

    def test_reports_how_many_images_left_the_gallery(self, tmp_path, capsys):
        self._library_with_a_deleted_photo(tmp_path)

        call_command("sync_library")

        assert "1 image(s) removed from the gallery" in capsys.readouterr().out
        assert models.Image.objects.count() == 0

    def test_dry_run_reports_without_removing_anything(self, tmp_path, capsys):
        self._library_with_a_deleted_photo(tmp_path)

        call_command("sync_library", "--dry-run-prune")

        captured = capsys.readouterr()
        assert "Would remove 1 of 1 image(s)" in captured.out
        assert FUJIFILM_FIXTURE.name in captured.out
        assert models.Image.objects.count() == 1

    def test_no_prune_removes_nothing(self, tmp_path, capsys):
        self._library_with_a_deleted_photo(tmp_path)

        call_command("sync_library", "--no-prune")

        assert models.Image.objects.count() == 1

    def test_rejects_conflicting_prune_flags(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("sync_library", "--no-prune", "--force-prune")

    def test_says_nothing_was_removed_when_a_folder_is_missing(self, tmp_path, capsys):
        LibraryFolderFactory(path=str(tmp_path / "does_not_exist"))

        call_command("sync_library")

        assert "Nothing was removed from the gallery" in capsys.readouterr().out


@pytest.mark.django_db
class TestSyncLibraryCommandSafetyGuard:
    @pytest.fixture(autouse=True)
    def _strict_guard(self, settings):
        settings.USE_ASYNC_TASKS = False
        settings.LIBRARY_PRUNE_GUARD_FRACTION = 0.5
        settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1

    def _library_emptied_on_disk(self, tmp_path):
        for fixture in (FUJIFILM_FIXTURE, FIXTURES_DIR / "XS107209.jpg", FIXTURES_DIR / "XS107336.jpg"):
            shutil.copy(fixture, tmp_path / fixture.name)
        LibraryFolderFactory(path=str(tmp_path))
        call_command("sync_library")
        for photo in tmp_path.iterdir():
            photo.unlink()

    def test_warns_and_removes_nothing_when_the_guard_trips(self, tmp_path, capsys):
        self._library_emptied_on_disk(tmp_path)

        call_command("sync_library")

        captured = capsys.readouterr()
        assert "Skipped removing 3 of 3 image(s)" in captured.out
        assert "--force-prune" in captured.out
        assert models.Image.objects.count() == 3

    def test_force_prune_overrides_the_guard(self, tmp_path, capsys):
        self._library_emptied_on_disk(tmp_path)

        call_command("sync_library", "--force-prune")

        assert models.Image.objects.count() == 0


@pytest.mark.django_db
class TestSyncLibraryCommandReportsPathChangeRemovals:
    @pytest.fixture(autouse=True)
    def _lite_mode(self, settings):
        settings.USE_ASYNC_TASKS = False
        settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1000

    def test_explains_removals_caused_by_a_narrowed_folder(self, tmp_path, capsys):
        inner = tmp_path / "2024"
        inner.mkdir()
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        shutil.copy(FIXTURES_DIR / "XS107209.jpg", inner / "keep.jpg")
        folder = LibraryFolderFactory(path=str(tmp_path))
        call_command("sync_library")

        update_library_folder_path(folder_id=folder.pk, path=str(inner))
        call_command("sync_library")

        captured = capsys.readouterr()
        assert "1 image(s) removed from the gallery" in captured.out
        assert "no longer inside any library folder" in captured.out
        assert "Their files are untouched." in captured.out
