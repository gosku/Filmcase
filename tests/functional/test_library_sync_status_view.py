import pytest

from src.data import models
from tests.factories import LibraryFolderFactory, SyncRunFactory


@pytest.mark.django_db
class TestLibraryFolderSyncStatus:
    def test_shows_not_synced_when_no_run_exists(self, client):
        folder = LibraryFolderFactory()

        response = client.get(f"/library/{folder.pk}/sync-status/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Not synced" in content
        assert "hx-trigger" not in content

    def test_shows_scanning_and_polls_while_active(self, client):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_SCANNING)

        response = client.get(f"/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Scanning" in content
        assert 'hx-trigger="every 2s"' in content

    def test_shows_progress_while_processing(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=4)
        run.processed = 1
        run.save(update_fields=["processed"])

        response = client.get(f"/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Processing 1/4" in content
        assert 'hx-trigger="every 2s"' in content
        assert "<progress" in content

    def test_shows_summary_and_stops_polling_when_completed(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=3)
        run.processed = 2
        run.skipped = 1
        run.save(update_fields=["processed", "skipped"])

        response = client.get(f"/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Imported 2" in content
        assert "skipped 1" in content
        assert "hx-trigger" not in content

    def test_shows_failed_state(self, client):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_FAILED)

        response = client.get(f"/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Sync failed" in content
        assert "hx-trigger" not in content
