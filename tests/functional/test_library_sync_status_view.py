import pytest

from src.data import models
from tests.factories import LibraryFolderFactory, SyncRunFactory


@pytest.mark.django_db
class TestLibraryFolderSyncStatus:
    def test_shows_not_synced_when_no_run_exists(self, client):
        folder = LibraryFolderFactory()

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Not synced" in content
        assert "hx-trigger" not in content

    def test_shows_scanning_and_polls_while_active(self, client):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_SCANNING)

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Scanning" in content
        assert 'hx-trigger="every 2s"' in content

    def test_shows_progress_while_processing(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=4)
        run.processed = 1
        run.save(update_fields=["processed"])

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Processing 1/4" in content
        assert 'hx-trigger="every 2s"' in content
        assert "<progress" in content

    def test_processing_label_counts_skipped_and_errors(self, client):
        # Regression: the label must show total handled (processed+skipped+errors),
        # not just processed — otherwise non-Fujifilm folders show "0/N" forever
        # while the progress bar advances.
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PROCESSING, total=10)
        run.processed = 0
        run.skipped = 3
        run.errors = 1
        run.save(update_fields=["processed", "skipped", "errors"])

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Processing 4/10" in content

    def test_shows_summary_and_stops_polling_when_completed(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=3)
        run.processed = 2
        run.skipped = 1
        run.save(update_fields=["processed", "skipped"])

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Imported 2" in content
        assert "skipped 1" in content
        assert "hx-trigger" not in content

    def test_shows_failed_state(self, client):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_FAILED)

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Sync failed" in content
        assert "hx-trigger" not in content


@pytest.mark.django_db
class TestLibraryFolderSyncStatusRemovals:
    def test_shows_removed_count_on_a_completed_run(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=2)
        run.record_removal_results(missing_found=3, uncovered_found=0, removed=3, skipped_reason="")

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        assert "removed 3" in response.content.decode()

    def test_polls_while_pruning(self, client):
        folder = LibraryFolderFactory()
        SyncRunFactory(folder=folder, state=models.SyncRun.STATE_PRUNING, total=2)

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Removing missing images" in content
        assert 'hx-trigger="every 2s"' in content

    def test_warns_when_the_guard_skipped_a_removal(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=0)
        run.record_removal_results(
            missing_found=30,
            uncovered_found=0,
            removed=0,
            skipped_reason=models.SyncRun.SKIPPED_GUARD,
        )

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Skipped removing 30 missing image" in content
        assert "--force-prune" in content

    def test_explains_a_folder_that_is_missing_from_disk(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_SCANNING)
        run.mark_failed(
            reason=models.SyncRun.FAILED_FOLDER_MISSING,
            message="Folder does not exist",
        )

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "Folder not found on disk" in content
        assert "Nothing was removed from the gallery" in content
        assert "Sync failed" not in content

    def test_still_reports_a_plain_failure_without_a_reason_code(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_SCANNING)
        run.mark_failed(reason="", message="something else went wrong")

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        assert "Sync failed" in response.content.decode()


@pytest.mark.django_db
class TestLibraryFolderSyncStatusUncovered:
    def test_explains_removals_caused_by_a_path_change(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=0)
        run.record_removal_results(
            missing_found=0, uncovered_found=2, removed=2, skipped_reason=""
        )

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "removed 2" in content
        assert "2 no longer in this folder" in content

    def test_says_nothing_extra_when_removals_were_only_missing_files(self, client):
        folder = LibraryFolderFactory()
        run = SyncRunFactory(folder=folder, state=models.SyncRun.STATE_COMPLETED, total=0)
        run.record_removal_results(
            missing_found=2, uncovered_found=0, removed=2, skipped_reason=""
        )

        response = client.get(f"/settings/library/{folder.pk}/sync-status/")

        content = response.content.decode()
        assert "removed 2" in content
        assert "no longer in this folder" not in content
