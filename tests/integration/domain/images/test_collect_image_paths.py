import os
import time

import pytest

from src.domain.images.queries import collect_image_paths


class TestCollectImagePaths:
    def test_returns_jpg_files(self, tmp_path):
        (tmp_path / "photo1.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "photo2.JPG").write_bytes(b"\xff\xd8")
        (tmp_path / "photo3.jpeg").write_bytes(b"\xff\xd8")
        (tmp_path / "document.pdf").write_bytes(b"%PDF")

        paths = collect_image_paths(folder=str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert "photo1.jpg" in filenames
        assert "photo2.JPG" in filenames
        assert "photo3.jpeg" in filenames
        assert "document.pdf" not in filenames

    def test_excludes_non_jpeg_files(self, tmp_path):
        (tmp_path / "photo.jpg").touch()
        (tmp_path / "photo.png").touch()
        (tmp_path / "document.txt").touch()

        paths = collect_image_paths(folder=str(tmp_path))

        assert paths == [str(tmp_path / "photo.jpg")]

    def test_returns_sorted_paths(self, tmp_path):
        (tmp_path / "c.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "a.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "b.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(folder=str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert filenames == sorted(filenames)

    def test_finds_files_recursively(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.jpg").write_bytes(b"\xff\xd8")
        (sub / "nested.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(folder=str(tmp_path))

        filenames = [os.path.basename(p) for p in paths]
        assert "top.jpg" in filenames
        assert "nested.jpg" in filenames

    def test_returns_absolute_paths(self, tmp_path):
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")

        paths = collect_image_paths(folder=str(tmp_path))

        for p in paths:
            assert os.path.isabs(p)

    def test_empty_folder_returns_empty_list(self, tmp_path):
        paths = collect_image_paths(folder=str(tmp_path))

        assert paths == []

    def test_nonexistent_folder_raises(self):
        with pytest.raises(FileNotFoundError):
            collect_image_paths(folder="/nonexistent/folder")

    def test_returns_files_from_a_directory_untouched_for_hours(self, tmp_path):
        # The walk used to skip directories whose mtime predated the folder's
        # last_checked_at. Nothing may depend on directory mtimes any more.
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
        long_ago = time.time() - 86400
        os.utime(tmp_path, (long_ago, long_ago))

        paths = collect_image_paths(folder=str(tmp_path))

        assert paths == [str(tmp_path / "photo.jpg")]

    def test_returns_files_from_a_renamed_subdirectory(self, tmp_path):
        # Renaming a directory updates its parent's mtime, never its own, so a
        # walk that skipped unchanged directories would miss the whole subtree
        # for good. Every image under it would then look deleted.
        original = tmp_path / "2024"
        original.mkdir()
        (original / "photo.jpg").write_bytes(b"\xff\xd8")
        long_ago = time.time() - 86400
        os.utime(original, (long_ago, long_ago))
        renamed = tmp_path / "2024-trip"
        original.rename(renamed)

        paths = collect_image_paths(folder=str(tmp_path))

        assert paths == [str(renamed / "photo.jpg")]
