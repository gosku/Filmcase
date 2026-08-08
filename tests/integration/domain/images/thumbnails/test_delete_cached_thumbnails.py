from pathlib import Path

from django.test import override_settings

from src.domain.images.thumbnails.operations import delete_cached_thumbnails
from src.domain.images.thumbnails.queries import thumbnail_cache_path

ORIGINAL = Path("/photos/2024/DSCF0001.JPG")


class TestDeleteCachedThumbnails:
    def test_removes_the_cache_file_for_every_configured_width(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path, THUMBNAIL_WIDTHS=(600, 1200)):
            cached = [thumbnail_cache_path(original_path=ORIGINAL, width=w) for w in (600, 1200)]
            for path in cached:
                path.write_bytes(b"\xff\xd8")

            removed = delete_cached_thumbnails(original_path=ORIGINAL)

            assert removed == 2
            assert not any(path.exists() for path in cached)

    def test_leaves_thumbnails_of_other_images_alone(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path, THUMBNAIL_WIDTHS=(600,)):
            other = Path("/photos/2024/DSCF0002.JPG")
            other_cache = thumbnail_cache_path(original_path=other, width=600)
            other_cache.write_bytes(b"\xff\xd8")
            thumbnail_cache_path(original_path=ORIGINAL, width=600).write_bytes(b"\xff\xd8")

            delete_cached_thumbnails(original_path=ORIGINAL)

            assert other_cache.exists()

    def test_reports_nothing_removed_when_no_thumbnail_was_cached(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path, THUMBNAIL_WIDTHS=(600,)):
            assert delete_cached_thumbnails(original_path=ORIGINAL) == 0

    def test_does_not_raise_when_the_cache_directory_is_absent(self, tmp_path):
        missing = tmp_path / "no_such_cache"

        with override_settings(THUMBNAIL_CACHE_DIR=missing, THUMBNAIL_WIDTHS=(600,)):
            assert delete_cached_thumbnails(original_path=ORIGINAL) == 0
