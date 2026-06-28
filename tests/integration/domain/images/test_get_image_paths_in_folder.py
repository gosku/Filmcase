from datetime import datetime, timedelta, timezone

import pytest

from src.domain.images.queries import get_image_paths_in_folder


class TestGetImagePathsInFolder:
    def test_returns_jpeg_files_in_folder(self, tmp_path):
        (tmp_path / "photo.jpg").touch()
        result = get_image_paths_in_folder(folder_path=str(tmp_path))
        assert result == [str(tmp_path / "photo.jpg")]

    def test_returns_jpeg_files_recursively_from_subdirectories(self, tmp_path):
        subdir = tmp_path / "2024"
        subdir.mkdir()
        (subdir / "photo.jpg").touch()
        result = get_image_paths_in_folder(folder_path=str(tmp_path))
        assert result == [str(subdir / "photo.jpg")]

    def test_excludes_non_jpeg_files(self, tmp_path):
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo.png").touch()
        (tmp_path / "document.txt").touch()
        result = get_image_paths_in_folder(folder_path=str(tmp_path))
        assert result == [str(tmp_path / "photo.jpg")]

    def test_raises_file_not_found_for_nonexistent_path(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FileNotFoundError):
            get_image_paths_in_folder(folder_path=missing)

    def test_skips_directory_unchanged_since_last_checked_at(self, tmp_path):
        (tmp_path / "photo.jpg").touch()
        # A last_checked_at in the future means the directory's mtime is older than it
        future = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        result = get_image_paths_in_folder(folder_path=str(tmp_path), last_checked_at=future)
        assert result == []

    def test_includes_directory_changed_after_last_checked_at(self, tmp_path):
        (tmp_path / "photo.jpg").touch()
        # A last_checked_at in the past means the directory's mtime is newer than it
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        result = get_image_paths_in_folder(folder_path=str(tmp_path), last_checked_at=past)
        assert result == [str(tmp_path / "photo.jpg")]

    def test_unchanged_parent_directory_does_not_block_changed_subdirectory(self, tmp_path):
        subdir = tmp_path / "2024"
        subdir.mkdir()
        (subdir / "photo.jpg").touch()
        # Set last_checked_at to between the parent dir creation and now.
        # Parent dir mtime predates last_checked_at (created before subdir touch),
        # but subdir mtime is after last_checked_at.
        import os, time
        past_mtime = time.time() - 3600
        os.utime(tmp_path, (past_mtime, past_mtime))
        last_checked = datetime.fromtimestamp(past_mtime + 1, tz=timezone.utc)

        result = get_image_paths_in_folder(folder_path=str(tmp_path), last_checked_at=last_checked)

        # Parent dir is skipped but subdir is NOT skipped (its mtime > last_checked_at)
        assert result == [str(subdir / "photo.jpg")]
