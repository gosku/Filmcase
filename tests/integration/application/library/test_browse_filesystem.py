import os
import pytest

from src.application.usecases.library.browse_filesystem import FolderNotFound, browse_filesystem
from src.application.usecases.library._dataclasses import FilesystemBrowseResult, FilesystemEntry


class TestBrowseFilesystem:
    def test_returns_immediate_subdirectories(self, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()

        result = browse_filesystem(path=str(tmp_path))

        assert isinstance(result, FilesystemBrowseResult)
        assert result.current_path == str(tmp_path)
        assert result.entries == (
            FilesystemEntry(name="alpha", path=str(tmp_path / "alpha")),
            FilesystemEntry(name="beta", path=str(tmp_path / "beta")),
        )

    def test_parent_path_is_set_for_nested_directory(self, tmp_path):
        subdir = tmp_path / "child"
        subdir.mkdir()

        result = browse_filesystem(path=str(subdir))

        assert result.parent_path == str(tmp_path)

    def test_parent_path_is_none_at_filesystem_root(self):
        result = browse_filesystem(path="/")
        assert result.parent_path is None

    def test_defaults_to_home_directory_when_path_is_empty(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        result = browse_filesystem(path="")
        assert result.current_path == str(tmp_path)

    def test_raises_folder_not_found_for_missing_path(self, tmp_path):
        missing = str(tmp_path / "does_not_exist")
        with pytest.raises(FolderNotFound) as exc_info:
            browse_filesystem(path=missing)
        assert exc_info.value.path == missing

    def test_entry_name_is_directory_basename(self, tmp_path):
        (tmp_path / "my_photos").mkdir()

        result = browse_filesystem(path=str(tmp_path))

        assert result.entries[0].name == "my_photos"
