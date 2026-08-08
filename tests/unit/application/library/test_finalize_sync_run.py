from unittest.mock import MagicMock, patch

import pytest

from src.application.usecases.library.finalize_sync_run import finalize_sync_run
from src.data import models
from src.domain.library.operations import PruneResult

_BEGIN = "src.application.usecases.library.finalize_sync_run.library_operations.begin_pruning"
_COMPLETE = "src.application.usecases.library.finalize_sync_run.library_operations.complete_sync_run"
_PRUNE = "src.application.usecases.library.finalize_sync_run.library_operations.prune_missing_images"
_GET_FOLDER = "src.application.usecases.library.finalize_sync_run.library_queries.get_library_folder"
_ALL_FOLDERS = "src.application.usecases.library.finalize_sync_run.library_queries.get_all_library_folders"
_ACTIVE_RUN = "src.application.usecases.library.finalize_sync_run.library_queries.get_active_sync_run"


def _pruned(*, removed: int = 1) -> PruneResult:
    return PruneResult(
        missing_found=removed,
        removed=removed,
        total=10,
        skipped_reason="",
        sample_paths=(),
    )


def _run(*, prune_mode: str = models.SyncRun.PRUNE_MODE_AUTO) -> MagicMock:
    run = MagicMock(spec=models.SyncRun)
    run.folder_id = 1
    run.prune_mode = prune_mode
    return run


@pytest.fixture
def _no_other_folders():
    with patch(_ALL_FOLDERS, return_value=[]):
        yield


class TestFinalizeSyncRun:
    def test_prunes_and_completes_when_it_wins_the_election(self, _no_other_folders):
        run = _run()
        with (
            patch(_BEGIN, return_value=True),
            patch(_GET_FOLDER),
            patch(_PRUNE, return_value=_pruned()) as prune,
            patch(_COMPLETE) as complete,
        ):
            finalize_sync_run(run=run)

        prune.assert_called_once()
        complete.assert_called_once_with(run=run)
        run.record_prune_result.assert_called_once_with(
            missing_found=1, removed=1, skipped_reason=""
        )

    def test_does_nothing_when_another_caller_won_the_election(self):
        run = _run()
        with (
            patch(_BEGIN, return_value=False),
            patch(_PRUNE) as prune,
            patch(_COMPLETE) as complete,
        ):
            finalize_sync_run(run=run)

        prune.assert_not_called()
        complete.assert_not_called()

    def test_completes_the_run_even_when_the_prune_raises(self, _no_other_folders):
        run = _run()
        with (
            patch(_BEGIN, return_value=True),
            patch(_GET_FOLDER),
            patch(_PRUNE, side_effect=OSError("disk went away")),
            patch(_COMPLETE) as complete,
        ):
            finalize_sync_run(run=run)

        complete.assert_called_once_with(run=run)

    def test_passes_the_runs_prune_mode_through(self, _no_other_folders):
        run = _run(prune_mode=models.SyncRun.PRUNE_MODE_FORCE)
        with (
            patch(_BEGIN, return_value=True),
            patch(_GET_FOLDER, return_value="folder"),
            patch(_PRUNE, return_value=_pruned()) as prune,
            patch(_COMPLETE),
        ):
            finalize_sync_run(run=run)

        assert prune.call_args.kwargs["mode"] == models.SyncRun.PRUNE_MODE_FORCE

    def test_defers_the_prune_while_another_folder_is_still_importing(self):
        run = _run()
        other = MagicMock(pk=2)
        still_importing = MagicMock()
        still_importing.all_images_accounted_for.return_value = False
        with (
            patch(_BEGIN, return_value=True),
            patch(_ALL_FOLDERS, return_value=[other]),
            patch(_ACTIVE_RUN, return_value=still_importing),
            patch(_PRUNE) as prune,
            patch(_COMPLETE) as complete,
        ):
            finalize_sync_run(run=run)

        prune.assert_not_called()
        complete.assert_called_once_with(run=run)
        run.record_prune_result.assert_called_once_with(
            missing_found=0, removed=0, skipped_reason=models.SyncRun.SKIPPED_DEFERRED
        )

    def test_prunes_when_another_folder_is_open_but_has_nothing_left_to_import(self):
        # A folder waiting only to finalise cannot re-point anything, so making
        # it block its neighbours would defer their removals for no gain.
        run = _run()
        other = MagicMock(pk=2)
        nothing_outstanding = MagicMock()
        nothing_outstanding.all_images_accounted_for.return_value = True
        with (
            patch(_BEGIN, return_value=True),
            patch(_ALL_FOLDERS, return_value=[other]),
            patch(_ACTIVE_RUN, return_value=nothing_outstanding),
            patch(_GET_FOLDER),
            patch(_PRUNE, return_value=_pruned()) as prune,
            patch(_COMPLETE),
        ):
            finalize_sync_run(run=run)

        prune.assert_called_once()

    def test_prunes_when_the_only_other_folder_is_idle(self):
        run = _run()
        other = MagicMock(pk=2)
        with (
            patch(_BEGIN, return_value=True),
            patch(_ALL_FOLDERS, return_value=[other]),
            patch(_ACTIVE_RUN, return_value=None),
            patch(_GET_FOLDER),
            patch(_PRUNE, return_value=_pruned()) as prune,
            patch(_COMPLETE),
        ):
            finalize_sync_run(run=run)

        prune.assert_called_once()
