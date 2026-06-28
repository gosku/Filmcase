import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from src.application.usecases.library.sync_library import CeleryWorkerUnavailable
from src.data import models
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
