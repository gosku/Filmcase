from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from django.test import override_settings

from src.application.usecases.images.process_images import (
    InvalidFolderError,
    import_images_from_folder,
)

FIXTURES_DIR = str(Path(__file__).resolve().parent.parent / "fixtures" / "images")

_IMPORT_UC = "src.interfaces.views.process_images_uc.import_images_from_folder"


class TestImportImagesFromFolderInvalidFolder:
    def test_raises_when_folder_does_not_exist_sync(self):
        with override_settings(USE_ASYNC_TASKS=False):
            with patch(
                "src.application.usecases.images.process_images.queries.collect_image_paths",
                side_effect=FileNotFoundError,
            ):
                with pytest.raises(InvalidFolderError):
                    import_images_from_folder(folder="/nonexistent/path")

    def test_raises_when_folder_does_not_exist_async(self):
        with override_settings(USE_ASYNC_TASKS=True):
            with patch(
                "src.application.usecases.images.process_images.queries.collect_image_paths",
                side_effect=FileNotFoundError,
            ):
                with pytest.raises(InvalidFolderError):
                    import_images_from_folder(folder="/nonexistent/path")


@pytest.mark.django_db
class TestImportFolderViewErrors:
    def test_missing_folder_returns_error(self, client):
        response = client.post(
            "/images/import/",
            {},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None

    def test_nonexistent_path_returns_error(self, client):
        response = client.post(
            "/images/import/",
            {"folder": "/nonexistent/path/that/does/not/exist"},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None

    def test_file_path_instead_of_directory_returns_error(self, client, tmp_path):
        f = tmp_path / "photo.jpg"
        f.write_bytes(b"")

        response = client.post(
            "/images/import/",
            {"folder": str(f)},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None


@pytest.mark.django_db
class TestImportFolderViewSuccess:
    def test_returns_success_partial_for_htmx_request(self, client):
        with patch(_IMPORT_UC, return_value=3) as mock_uc:
            response = client.post(
                "/images/import/",
                {"folder": FIXTURES_DIR},
                HTTP_HX_REQUEST="true",
            )

        assert response.status_code == 200
        mock_uc.assert_called_once_with(folder=FIXTURES_DIR)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--success") is not None

    def test_success_message_shows_imported_count(self, client):
        with patch(_IMPORT_UC, return_value=5):
            response = client.post(
                "/images/import/",
                {"folder": FIXTURES_DIR},
                HTTP_HX_REQUEST="true",
            )

        assert "5 images imported" in response.content.decode()

    def test_empty_folder_returns_empty_state(self, client, tmp_path):
        with patch(_IMPORT_UC, return_value=0):
            response = client.post(
                "/images/import/",
                {"folder": str(tmp_path)},
                HTTP_HX_REQUEST="true",
            )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--empty") is not None

    def test_unexpected_exception_returns_error(self, client):
        with patch(_IMPORT_UC, side_effect=RuntimeError("boom")):
            response = client.post(
                "/images/import/",
                {"folder": FIXTURES_DIR},
                HTTP_HX_REQUEST="true",
            )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None


@pytest.mark.django_db
class TestImportFolderViewIntegration:
    """End-to-end: real fixture images processed through the full stack."""

    def test_imports_all_fujifilm_jpegs_in_fixtures(self, client):
        from src.data.models import Image

        response = client.post(
            "/images/import/",
            {"folder": FIXTURES_DIR},
            HTTP_HX_REQUEST="true",
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--success") is not None
        assert Image.objects.count() > 0
