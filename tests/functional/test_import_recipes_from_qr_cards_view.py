from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.data import models

CARDS_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "recipe_cards"
IMAGE_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "images"


def _fixture_upload(directory: Path, filename: str) -> BytesIO:
    path = directory / filename
    buffer = BytesIO(path.read_bytes())
    buffer.name = filename
    return buffer


def _post(client, *filenames: str):
    files = [_fixture_upload(CARDS_FIXTURES_DIR, f) for f in filenames]
    data = {"images": files} if len(files) > 1 else {"images": files[0]}
    return client.post("/recipes/import-qr-cards/", data, format="multipart")


@pytest.mark.django_db
class TestRecipesExplorerImportCardsOption:
    def test_import_cards_option_is_present(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(
            "button",
            class_="open-import-modal-btn",
            attrs={"data-import-url": "/recipes/import-qr-cards/"},
        )
        assert btn is not None

    def test_both_import_openers_retarget_the_shared_modal(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        openers = soup.find_all("button", class_="open-import-modal-btn")
        urls = {btn.get("data-import-url") for btn in openers}
        assert urls == {"/recipes/import/", "/recipes/import-qr-cards/"}
        titles = {btn.get("data-import-title") for btn in openers}
        assert len(titles) == 2
        descs = {btn.get("data-import-desc") for btn in openers}
        assert len(descs) == 2


@pytest.mark.django_db
class TestImportRecipesFromQRCardsViewMethodGuard:
    def test_get_returns_405(self, client):
        response = client.get("/recipes/import-qr-cards/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestImportRecipesFromQRCardsViewSuccess:
    def test_returns_200(self, client):
        response = _post(client, "card_classic_chrome.jpg")
        assert response.status_code == 200

    def test_creates_recipe_in_db(self, client):
        assert models.FujifilmRecipe.objects.count() == 0
        _post(client, "card_classic_chrome.jpg")
        assert models.FujifilmRecipe.objects.count() == 1

    def test_response_shows_import_count(self, client):
        response = _post(client, "card_classic_chrome.jpg")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "1 recipe" in soup.get_text().lower()

    def test_imports_multiple_cards(self, client):
        response = _post(client, "card_classic_chrome.jpg", "card_acros.jpg")
        assert response.status_code == 200
        assert models.FujifilmRecipe.objects.count() == 2
        soup = BeautifulSoup(response.content, "html.parser")
        assert "2 recipe" in soup.get_text().lower()

    def test_deduplicates_same_card(self, client):
        _post(client, "card_classic_chrome.jpg")
        _post(client, "card_classic_chrome.jpg")
        assert models.FujifilmRecipe.objects.count() == 1


@pytest.mark.django_db
class TestImportRecipesFromQRCardsViewFailure:
    def test_no_files_returns_error_message(self, client):
        response = client.post("/recipes/import-qr-cards/", {})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None

    def test_image_without_qr_shows_failure(self, client):
        non_card = _fixture_upload(IMAGE_FIXTURES_DIR, "XS107114.JPG")
        response = client.post(
            "/recipes/import-qr-cards/", {"images": non_card}, format="multipart",
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "XS107114.JPG" in soup.get_text()

    def test_unexpected_exception_shows_error_message(self, client):
        with patch(
            "src.application.usecases.recipes.import_recipes_from_uploaded_qr_cards.import_recipes_from_uploaded_qr_cards",
            side_effect=RuntimeError("boom"),
        ):
            response = _post(client, "card_classic_chrome.jpg")
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="import-result--error") is not None
        assert "unexpected" in soup.get_text().lower()
