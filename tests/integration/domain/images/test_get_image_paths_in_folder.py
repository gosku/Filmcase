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
