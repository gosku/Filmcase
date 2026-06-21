from pathlib import Path

import pytest
from django.test import override_settings

from src.domain.images.thumbnails.queries import thumbnail_cache_path, thumbnail_content_type


@pytest.mark.django_db
class TestThumbnailCachePath:
    def test_returns_path_inside_cache_dir(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            result = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=600)
        assert result.parent == tmp_path

    def test_preserves_original_suffix(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            jpg = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=600)
            png = thumbnail_cache_path(original_path=Path("/shots/img.png"), width=600)
        assert jpg.suffix == ".jpg"
        assert png.suffix == ".png"

    def test_same_inputs_produce_same_path(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            a = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=600)
            b = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=600)
        assert a == b

    def test_different_paths_produce_different_hashes(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            a = thumbnail_cache_path(original_path=Path("/shots/img1.jpg"), width=600)
            b = thumbnail_cache_path(original_path=Path("/shots/img2.jpg"), width=600)
        assert a != b

    def test_different_widths_produce_different_hashes(self, tmp_path):
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            a = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=300)
            b = thumbnail_cache_path(original_path=Path("/shots/img.jpg"), width=600)
        assert a != b


class TestThumbnailContentType:
    def test_jpg_returns_image_jpeg(self):
        assert thumbnail_content_type(cache_path=Path("thumb.jpg")) == "image/jpeg"

    def test_jpeg_returns_image_jpeg(self):
        assert thumbnail_content_type(cache_path=Path("thumb.jpeg")) == "image/jpeg"

    def test_png_returns_image_png(self):
        assert thumbnail_content_type(cache_path=Path("thumb.png")) == "image/png"

    def test_unknown_extension_defaults_to_image_jpeg(self):
        assert thumbnail_content_type(cache_path=Path("thumb.unknownxyz")) == "image/jpeg"
