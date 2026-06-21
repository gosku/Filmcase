import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestCreateRecipeCardsBatchViewMethodGuard:
    def test_get_returns_405(self, client) -> None:
        response = client.get("/recipes/cards/batch/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestCreateRecipeCardsBatchExplorerPresence:
    def test_action_button_is_in_actions_dropdown(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("button", id="ms-create-cards-btn") is not None

    def test_modal_is_in_page(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="create-cards-overlay") is not None

    def test_form_posts_to_correct_url(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="create-cards-form")
        assert form is not None
        assert form.get("hx-post") == "/recipes/cards/batch/"


@pytest.mark.django_db
class TestCreateRecipeCardsBatchViewSuccess:
    def test_returns_200_and_created_count(self, client, tmp_path, settings) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()

        response = client.post(
            "/recipes/cards/batch/",
            {"recipe_ids": [recipe_a.pk, recipe_b.pk]},
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "2 recipe card" in soup.get_text().lower()
        assert soup.find(attrs={"data-all-succeeded": "true"}) is not None

    def test_response_includes_working_download_link(
        self, client, tmp_path, settings
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()

        response = client.post("/recipes/cards/batch/", {"recipe_ids": [recipe.pk]})

        soup = BeautifulSoup(response.content, "html.parser")
        link = soup.find("a", class_="remove-result__download-btn")
        assert link is not None
        zip_name = link["href"].rstrip("/").split("/")[-1]
        assert (Path(tempfile.gettempdir()) / zip_name).exists()


@pytest.mark.django_db
class TestCreateRecipeCardsBatchViewFailure:
    def test_not_found_id_shows_failure_and_no_link(
        self, client, tmp_path, settings
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)

        response = client.post("/recipes/cards/batch/", {"recipe_ids": [999999]})

        soup = BeautifulSoup(response.content, "html.parser")
        assert "not found" in soup.get_text().lower()
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None
        assert soup.find("a", class_="remove-result__download-btn") is None

    def test_partial_failure_still_creates_cards_for_valid_recipes(
        self, client, tmp_path, settings
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()

        response = client.post(
            "/recipes/cards/batch/",
            {"recipe_ids": [recipe.pk, 999999]},
        )

        soup = BeautifulSoup(response.content, "html.parser")
        assert "1 recipe card" in soup.get_text().lower()
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None
        assert soup.find("a", class_="remove-result__download-btn") is not None

    def test_invalid_recipe_ids_returns_400(self, client) -> None:
        response = client.post("/recipes/cards/batch/", {"recipe_ids": ["abc"]})
        assert response.status_code == 400

    def test_unexpected_exception_shows_error_message(
        self, client, tmp_path, settings
    ) -> None:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        with patch(
            "src.interfaces.recipes.views.create_recipe_cards_batch_uc.create_recipe_cards_batch",
            side_effect=RuntimeError("boom"),
        ):
            response = client.post(
                "/recipes/cards/batch/", {"recipe_ids": [recipe.pk]}
            )
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "unexpected" in soup.get_text().lower()


@pytest.mark.django_db
class TestRecipeCardsZipDownloadView:
    def _create_zip(self, client, tmp_path, settings) -> str:
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post("/recipes/cards/batch/", {"recipe_ids": [recipe.pk]})
        soup = BeautifulSoup(response.content, "html.parser")
        link = soup.find("a", class_="remove-result__download-btn")
        return link["href"]

    def test_download_returns_zip_attachment(
        self, client, tmp_path, settings
    ) -> None:
        url = self._create_zip(client, tmp_path, settings)

        response = client.get(url)

        assert response.status_code == 200
        assert response["Content-Type"] == "application/zip"
        assert "attachment" in response["Content-Disposition"]

    def test_path_traversal_filename_is_rejected(self, client) -> None:
        response = client.get("/recipes/cards/zip/..%2F..%2Fetc%2Fpasswd/")
        assert response.status_code == 404

    def test_unknown_zip_returns_404(self, client) -> None:
        response = client.get("/recipes/cards/zip/recipe_cards_deadbeef.zip/")
        assert response.status_code == 404
