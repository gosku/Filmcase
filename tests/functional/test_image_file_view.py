from pathlib import Path

import pytest
from django.test import override_settings

from src.data.models import Image

FIXTURE_IMAGE = Path(__file__).resolve().parent.parent / "fixtures" / "images" / "XS107114.JPG"


@pytest.mark.django_db
class TestImageFileView:
    def test_returns_200_for_existing_file(self, tmp_path):
        image = Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))
        response = self._client().get(f"/images/file/{image.id}/")
        assert response.status_code == 200

    def test_returns_image_content_type(self, tmp_path):
        image = Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))
        response = self._client().get(f"/images/file/{image.id}/")
        assert response["Content-Type"].startswith("image/")

    def test_returns_404_for_missing_image_record(self):
        response = self._client().get("/images/file/99999/")
        assert response.status_code == 404

    def test_returns_404_when_file_missing_from_disk(self):
        image = Image.objects.create(filename="ghost.JPG", filepath="/nonexistent/ghost.JPG")
        response = self._client().get(f"/images/file/{image.id}/")
        assert response.status_code == 404

    def test_returns_200_for_resized_image(self, tmp_path):
        image = Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))
        with override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            response = self._client().get(f"/images/file/{image.id}/", {"width": "300"})
        assert response.status_code == 200

    def test_returns_404_for_invalid_width_param(self):
        image = Image.objects.create(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))
        response = self._client().get(f"/images/file/{image.id}/", {"width": "notanumber"})
        assert response.status_code == 404

    def _client(self):
        from django.test import Client
        return Client()
