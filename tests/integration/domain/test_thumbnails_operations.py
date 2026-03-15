from pathlib import Path

import pytest
from django.test import override_settings
from PIL import Image as PILImage

from src.domain.images.thumbnails.operations import generate_thumbnail
from src.domain.images.thumbnails.queries import thumbnail_cache_path

FIXTURE_IMAGE = Path(__file__).resolve().parent.parent.parent / "fixtures" / "images" / "XS107114.JPG"


class TestGenerateThumbnail:
    def test_creates_file_at_cache_path(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            result = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
        assert result.is_file()

    def test_returned_path_matches_cache_path(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            result = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
            expected = thumbnail_cache_path(original_path=FIXTURE_IMAGE, width=300)
        assert result == expected

    def test_thumbnail_width_does_not_exceed_requested_width(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            result = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
        with PILImage.open(result) as img:
            assert img.width <= 300

    def test_thumbnail_preserves_aspect_ratio(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            result = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
        with PILImage.open(FIXTURE_IMAGE) as original:
            original_ratio = original.width / original.height
        with PILImage.open(result) as thumb:
            thumb_ratio = thumb.width / thumb.height
        assert abs(original_ratio - thumb_ratio) < 0.01

    def test_second_call_returns_cached_file_without_regenerating(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            first = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
            mtime_after_first = first.stat().st_mtime
            second = generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
            mtime_after_second = second.stat().st_mtime
        assert first == second
        assert mtime_after_first == mtime_after_second

    def test_different_widths_produce_different_cache_files(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            small = generate_thumbnail(original_path=FIXTURE_IMAGE, width=100)
            large = generate_thumbnail(original_path=FIXTURE_IMAGE, width=400)
        assert small != large
        with PILImage.open(small) as img:
            assert img.width <= 100
        with PILImage.open(large) as img:
            assert img.width <= 400

    def test_creates_cache_dir_if_missing(self, tmp_path):
        cache_dir = tmp_path / "new" / "nested" / "dir"
        assert not cache_dir.exists()
        with override_settings(THUMBNAIL_CACHE_DIR=cache_dir):
            generate_thumbnail(original_path=FIXTURE_IMAGE, width=300)
        assert cache_dir.is_dir()
