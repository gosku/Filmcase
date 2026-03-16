from pathlib import Path

import pytest
from django.core.management import call_command
from django.test import override_settings

from src.data.models import Image
from src.domain.images.thumbnails.queries import thumbnail_cache_path

FIXTURE_IMAGE = Path(__file__).resolve().parent.parent / "fixtures" / "images" / "XS107114.JPG"
THUMBNAIL_WIDTH = 600


@pytest.mark.django_db
class TestGenerateThumbnailsCommand:
    def test_generates_thumbnail_for_each_image(self, tmp_path, capsys):
        Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            call_command("generate_thumbnails")

        captured = capsys.readouterr()
        assert "enqueued=1" in captured.out
        assert "already_cached=0" in captured.out

    def test_thumbnail_file_is_created_on_disk(self, tmp_path):
        Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            call_command("generate_thumbnails")
            expected = thumbnail_cache_path(original_path=FIXTURE_IMAGE, width=THUMBNAIL_WIDTH)

        assert expected.is_file()

    def test_reports_missing_file_to_stderr(self, tmp_path, capsys):
        Image.objects.create(filename="ghost.JPG", filepath="/nonexistent/ghost.JPG")

        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            call_command("generate_thumbnails")

        captured = capsys.readouterr()
        assert "Missing file" in captured.err
        assert "/nonexistent/ghost.JPG" in captured.err
        assert "missing=1" in captured.out

    def test_skips_already_cached_thumbnails(self, tmp_path, capsys):
        Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            call_command("generate_thumbnails")
            capsys.readouterr()  # discard first run output
            call_command("generate_thumbnails")

        captured = capsys.readouterr()
        assert "already_cached=1" in captured.out
        assert "enqueued=0" in captured.out
