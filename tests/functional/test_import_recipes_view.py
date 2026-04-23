from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.data import models

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"


def _fixture_upload(filename: str):
    """Return a file-like object from a fixture image, suitable for client.post FILES."""
    path = FIXTURES_DIR / filename
    return BytesIO(path.read_bytes())


def _post(client, *filenames):
    files = [_fixture_upload(f) for f in filenames]
    data = {"images": files} if len(files) > 1 else {"images": files[0]}
    return client.post("/recipes/import/", data, format="multipart")


# ---------------------------------------------------------------------------
# Explorer page — Create Recipes button presence
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesExplorerCreateButton:
    def test_create_recipes_button_is_present(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find("button", id="create-recipes-btn")
        assert btn is not None

    def test_import_recipes_option_is_present(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(
            "button",
            class_="open-import-modal-btn",
            attrs={"data-import-url": "/recipes/import/"},
        )
        assert btn is not None

    def test_import_modal_is_in_page(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="import-overlay") is not None

    def test_import_form_posts_to_correct_url(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="import-form")
        assert form is not None
        assert form.get("hx-post") == "/recipes/import/"


# ---------------------------------------------------------------------------
# Import view — method guard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestImportRecipesViewMethodGuard:
    def test_get_returns_405(self, client):
        response = client.get("/recipes/import/")
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Import view — success cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestImportRecipesViewSuccess:
    def test_returns_200(self, client):
        response = _post(client, "XS107114.JPG")
        assert response.status_code == 200

    def test_creates_recipe_in_db(self, client):
        assert models.FujifilmRecipe.objects.count() == 0
        _post(client, "XS107114.JPG")
        assert models.FujifilmRecipe.objects.count() == 1

    def test_response_shows_import_count(self, client):
        response = _post(client, "XS107114.JPG")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "1 recipe" in soup.get_text().lower()

    def test_response_has_no_error(self, client):
        response = _post(client, "XS107114.JPG")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is None

    def test_imports_multiple_files(self, client):
        response = _post(client, "XS107114.JPG", "XS107209.jpg")
        assert response.status_code == 200
        assert models.FujifilmRecipe.objects.count() >= 1
        soup = BeautifulSoup(response.content, "html.parser")
        assert "2 recipe" in soup.get_text().lower()

    def test_deduplicates_same_recipe(self, client):
        _post(client, "XS107114.JPG")
        _post(client, "XS107114.JPG")
        assert models.FujifilmRecipe.objects.count() == 1


# ---------------------------------------------------------------------------
# Import view — failure cases
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestImportRecipesViewFailure:
    def test_no_files_returns_error_message(self, client):
        response = client.post("/recipes/import/", {})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None

    def test_non_fujifilm_file_shows_failure(self, client):
        data = {"images": BytesIO(b"\xff\xd8\xff\xd9")}
        # Give it a name so the view can identify it
        data["images"].name = "not_fujifilm.jpg"
        response = client.post("/recipes/import/", data, format="multipart")
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "not_fujifilm.jpg" in soup.get_text()

    def test_partial_failure_reports_both_success_and_failure(self, client):
        bad = BytesIO(b"\xff\xd8\xff\xd9")
        bad.name = "bad.jpg"
        good = _fixture_upload("XS107114.JPG")
        good.name = "XS107114.JPG"
        response = client.post("/recipes/import/", {"images": [bad, good]}, format="multipart")
        assert response.status_code == 200
        text = BeautifulSoup(response.content, "html.parser").get_text()
        assert "1 recipe" in text.lower()
        assert "bad.jpg" in text

    def test_unexpected_exception_shows_error_message(self, client):
        with patch(
            "src.application.usecases.recipes.import_recipes_from_uploaded_files.import_recipes_from_uploaded_files",
            side_effect=RuntimeError("boom"),
        ):
            response = _post(client, "XS107114.JPG")
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None
        assert "unexpected" in soup.get_text().lower()
