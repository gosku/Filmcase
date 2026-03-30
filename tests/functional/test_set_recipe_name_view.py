import pytest
from bs4 import BeautifulSoup
from unittest.mock import patch

from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestSetRecipeNameView:
    def test_returns_404_for_nonexistent_recipe(self, client):
        response = client.post("/recipes/99999/set-name/", {"name": "Test"})
        assert response.status_code == 404

    def test_happy_path_sets_name_in_db(self, client):
        recipe = FujifilmRecipeFactory(name="")
        client.post(f"/recipes/{recipe.id}/set-name/", {"name": "My Recipe"})
        recipe.refresh_from_db()
        assert recipe.name == "My Recipe"

    def test_happy_path_returns_name_row_partial(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "My Recipe"})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "My Recipe" in soup.get_text()

    def test_happy_path_response_has_no_error(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "My Recipe"})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="recipe-name-error") is None

    def test_validation_error_name_too_long(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "X" * 26})
        assert response.status_code == 200
        recipe.refresh_from_db()
        assert recipe.name == ""
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="recipe-name-error") is not None

    def test_validation_error_non_ascii_name(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "caf\xe9"})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="recipe-name-error") is not None

    def test_validation_error_shows_form(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "X" * 26})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="recipe-name-form-state") is not None

    def test_unexpected_exception_shows_message(self, client):
        recipe = FujifilmRecipeFactory(name="")
        with patch("src.domain.images.operations.set_recipe_name", side_effect=RuntimeError("boom")):
            response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "Test"})
        assert response.status_code == 200
        assert b"something unexpected happened" in response.content.lower()

    def test_unexpected_exception_shows_form(self, client):
        recipe = FujifilmRecipeFactory(name="")
        with patch("src.domain.images.operations.set_recipe_name", side_effect=RuntimeError("boom")):
            response = client.post(f"/recipes/{recipe.id}/set-name/", {"name": "Test"})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="recipe-name-error") is not None
