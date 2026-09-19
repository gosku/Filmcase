import pytest

from src.data import models
from tests.factories import LibraryFolderFactory, SyncRunFactory


@pytest.mark.django_db
class TestSyncRunCreateRemoval:
    def test_creates_a_run_in_the_removing_state(self) -> None:
        folder = LibraryFolderFactory()

        run = models.SyncRun.create_removal(folder=folder)

        assert run.state == models.SyncRun.STATE_REMOVING
        assert run.folder_id == folder.pk

    def test_leaves_the_total_unknown(self) -> None:
        folder = LibraryFolderFactory()

        run = models.SyncRun.create_removal(folder=folder)

        assert run.total is None

    def test_removing_counts_as_an_active_state(self) -> None:
        assert models.SyncRun.STATE_REMOVING in models.SyncRun.ACTIVE_STATES


@pytest.mark.django_db
class TestSyncRunSetRemovalTotal:
    def test_sets_the_total_without_leaving_the_removing_state(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=None)

        run.set_removal_total(total=7)

        run.refresh_from_db()
        assert run.total == 7
        assert run.state == models.SyncRun.STATE_REMOVING


@pytest.mark.django_db
class TestSyncRunRecordImageRemoved:
    def test_increments_the_removed_count(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=2)

        run.record_image_removed()

        run.refresh_from_db()
        assert run.removed == 1

    def test_increments_are_cumulative(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=2)

        run.record_image_removed()
        run.record_image_removed()

        run.refresh_from_db()
        assert run.removed == 2


@pytest.mark.django_db
class TestSyncRunAllRemovalsAccountedFor:
    def test_is_false_while_the_total_is_unknown(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=None)

        assert run.all_removals_accounted_for() is False

    def test_is_false_while_images_are_still_pending(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=2, removed=1)

        assert run.all_removals_accounted_for() is False

    def test_is_true_once_every_image_is_removed(self) -> None:
        run = SyncRunFactory(state=models.SyncRun.STATE_REMOVING, total=2, removed=2)

        assert run.all_removals_accounted_for() is True
