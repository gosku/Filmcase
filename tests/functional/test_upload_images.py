import io
from pathlib import Path

import pytest
from django.test import override_settings

from src.data.models import Image

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"
FUJIFILM_JPEG = FIXTURES_DIR / "XS105026.JPG"


@pytest.mark.django_db
class TestUploadImagesView:

    def test_rejects_get_requests(self, client, tmp_path):
        with override_settings(UPLOAD_DIR=tmp_path):
            response = client.get("/images/upload/")
        assert response.status_code == 405

    def test_returns_400_when_no_files(self, client, tmp_path):
        with override_settings(UPLOAD_DIR=tmp_path):
            response = client.post("/images/upload/")
        assert response.status_code == 400
        assert "error" in response.json()

    def test_processes_valid_fujifilm_jpeg(self, client, tmp_path):
        with override_settings(UPLOAD_DIR=tmp_path):
            with FUJIFILM_JPEG.open("rb") as f:
                response = client.post("/images/upload/", {"images": f})

        assert response.status_code == 200
        data = response.json()
        assert FUJIFILM_JPEG.name in data["processed"]
        assert data["skipped"] == []
        assert Image.objects.filter(filename=FUJIFILM_JPEG.name).exists()

    def test_skips_non_jpeg_files(self, client, tmp_path):
        fake_txt = io.BytesIO(b"not an image")
        fake_txt.name = "notes.txt"
        with override_settings(UPLOAD_DIR=tmp_path):
            response = client.post("/images/upload/", {"images": fake_txt})

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] == []
        assert "notes.txt" in data["skipped"]

    def test_skips_non_fujifilm_jpeg(self, client, tmp_path):
        # A valid JPEG header but no Fujifilm EXIF → NoFilmSimulationError
        minimal_jpeg = io.BytesIO(bytes([0xFF, 0xD8, 0xFF, 0xD9]))
        minimal_jpeg.name = "other-brand.jpg"
        with override_settings(UPLOAD_DIR=tmp_path):
            response = client.post("/images/upload/", {"images": minimal_jpeg})

        assert response.status_code == 200
        data = response.json()
        assert "other-brand.jpg" in data["skipped"]
        assert data["processed"] == []

    def test_saves_file_to_upload_dir(self, client, tmp_path):
        with override_settings(UPLOAD_DIR=tmp_path):
            with FUJIFILM_JPEG.open("rb") as f:
                client.post("/images/upload/", {"images": f})

        assert (tmp_path / FUJIFILM_JPEG.name).exists()

    def test_processes_multiple_files(self, client, tmp_path):
        jpeg_files = list(FIXTURES_DIR.glob("*.JPG"))[:2]
        with override_settings(UPLOAD_DIR=tmp_path):
            files = [f.open("rb") for f in jpeg_files]
            try:
                response = client.post("/images/upload/", {"images": files})
            finally:
                for f in files:
                    f.close()

        data = response.json()
        assert len(data["processed"]) + len(data["skipped"]) == len(jpeg_files)
