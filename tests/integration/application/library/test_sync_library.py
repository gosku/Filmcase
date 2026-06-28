import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import time_machine
from django.test import override_settings

from src.application.usecases.library.sync_library import (
    CeleryWorkerUnavailable,
    SyncLibraryResult,
    sync_library,
)
from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FUJIFILM_FIXTURE = FIXTURES_DIR / "XS107114.JPG"
NON_FUJIFILM_FIXTURE = FIXTURES_DIR / "sub-folder" / "img_4968_dng_embedded.jpg"

FROZEN_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.django_db
class TestSyncLibraryEmptyLibrary:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_returns_zero_result_when_no_folders_are_registered(self):
        result = sync_library()
        assert result == SyncLibraryResult(
            folders_scanned=0,
            new_files_found=0,
            skipped_non_fujifilm=0,
            missing_folders=(),
        )


@pytest.mark.django_db
class TestSyncLibraryNewImages:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_processes_new_fujifilm_images_found_in_registered_folder(self, tmp_path):
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))

        result = sync_library()

        assert result.new_files_found == 1
        assert result.skipped_non_fujifilm == 0
        assert models.Image.objects.filter(filepath=str(tmp_path / FUJIFILM_FIXTURE.name)).exists()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_result_type_is_sync_library_result(self, tmp_path):
        LibraryFolderFactory(path=str(tmp_path))
        result = sync_library()
        assert isinstance(result, SyncLibraryResult)


@pytest.mark.django_db
class TestSyncLibraryAlreadyKnownImages:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_skips_images_already_in_db(self, tmp_path):
        filepath = str(tmp_path / "photo.jpg")
        (tmp_path / "photo.jpg").touch()
        ImageFactory(filepath=filepath)
        LibraryFolderFactory(path=str(tmp_path))

        result = sync_library()

        assert result.new_files_found == 0


@pytest.mark.django_db
class TestSyncLibraryMissingFolder:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_records_missing_folder_in_result(self, tmp_path):
        missing_path = str(tmp_path / "does_not_exist")
        LibraryFolderFactory(path=missing_path)

        result = sync_library()

        assert missing_path in result.missing_folders

    @override_settings(USE_ASYNC_TASKS=False)
    def test_continues_scanning_other_folders_when_one_is_missing(self, tmp_path):
        missing_path = str(tmp_path / "does_not_exist")
        good_path = tmp_path / "good"
        good_path.mkdir()
        LibraryFolderFactory(path=missing_path)
        LibraryFolderFactory(path=str(good_path))

        result = sync_library()

        assert result.folders_scanned == 2
        assert missing_path in result.missing_folders


@pytest.mark.django_db
class TestSyncLibraryTimestamps:
    @override_settings(USE_ASYNC_TASKS=False)
    @time_machine.travel(FROZEN_NOW, tick=False)
    def test_last_checked_at_is_set_after_sync(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        assert folder.last_checked_at is None

        sync_library()

        folder.refresh_from_db()
        assert folder.last_checked_at == FROZEN_NOW

    @override_settings(USE_ASYNC_TASKS=False)
    @time_machine.travel(FROZEN_NOW, tick=False)
    def test_last_processed_at_is_set_when_new_files_are_found(self, tmp_path):
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_library()

        folder.refresh_from_db()
        assert folder.last_processed_at == FROZEN_NOW

    @override_settings(USE_ASYNC_TASKS=False)
    @time_machine.travel(FROZEN_NOW, tick=False)
    def test_last_processed_at_is_not_set_when_no_new_files_are_found(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        sync_library()

        folder.refresh_from_db()
        assert folder.last_processed_at is None

    @override_settings(USE_ASYNC_TASKS=False)
    @time_machine.travel(FROZEN_NOW, tick=False)
    def test_last_checked_at_is_set_for_missing_folder(self, tmp_path):
        missing_path = str(tmp_path / "does_not_exist")
        folder = LibraryFolderFactory(path=missing_path)

        sync_library()

        folder.refresh_from_db()
        assert folder.last_checked_at == FROZEN_NOW


@pytest.mark.django_db
class TestSyncLibraryOverlappingFolders:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_image_in_child_folder_is_processed_only_once(self, tmp_path):
        child = tmp_path / "sub"
        child.mkdir()
        shutil.copy(FUJIFILM_FIXTURE, child / FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))
        LibraryFolderFactory(path=str(child))

        result = sync_library()

        assert result.new_files_found == 1
        assert models.Image.objects.filter(
            filepath=str(child / FUJIFILM_FIXTURE.name)
        ).count() == 1


@pytest.mark.django_db
class TestSyncLibraryNonFujifilmImages:
    @override_settings(USE_ASYNC_TASKS=False)
    def test_non_fujifilm_image_is_counted_as_skipped_in_sync_mode(self, tmp_path):
        shutil.copy(NON_FUJIFILM_FIXTURE, tmp_path / NON_FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))

        result = sync_library()

        assert result.skipped_non_fujifilm == 1
        assert result.new_files_found == 0

    @override_settings(USE_ASYNC_TASKS=False)
    def test_non_fujifilm_image_does_not_abort_sync(self, tmp_path):
        shutil.copy(NON_FUJIFILM_FIXTURE, tmp_path / NON_FUJIFILM_FIXTURE.name)
        shutil.copy(FUJIFILM_FIXTURE, tmp_path / FUJIFILM_FIXTURE.name)
        LibraryFolderFactory(path=str(tmp_path))

        result = sync_library()

        assert result.skipped_non_fujifilm == 1
        assert result.new_files_found == 1


@pytest.mark.django_db
class TestSyncLibraryCeleryWorkerUnavailable:
    def test_raises_when_async_is_enabled_and_no_worker_is_reachable(self):
        with patch("src.services.workertasks.is_celery_worker_available", return_value=False):
            with override_settings(USE_ASYNC_TASKS=True):
                with pytest.raises(CeleryWorkerUnavailable):
                    sync_library()

    @override_settings(USE_ASYNC_TASKS=False)
    def test_does_not_check_worker_when_async_is_disabled(self, tmp_path):
        with patch("src.services.workertasks.is_celery_worker_available") as mock_check:
            sync_library()
        mock_check.assert_not_called()
