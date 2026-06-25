from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.data import models
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRemoveRecipesViewMethodGuard:
    def test_get_returns_405(self, client) -> None:
        response = client.get("/recipes/delete/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestRemoveRecipesExplorerPresence:
    def test_delete_action_button_is_in_actions_dropdown(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find("button", id="ms-delete-recipes-btn")
        assert btn is not None

    def test_delete_recipes_modal_is_in_page(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="delete-recipes-overlay") is not None

    def test_delete_form_posts_to_correct_url(self, client) -> None:
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="delete-recipes-form")
        assert form is not None
        assert form.get("hx-post") == "/recipes/delete/"


@pytest.mark.django_db
class TestRemoveRecipesViewSuccess:
    def test_returns_200(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.post("/recipes/delete/", {"recipe_ids": [recipe.pk]})
        assert response.status_code == 200

    def test_deletes_two_of_three_selected_recipes(self, client) -> None:
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        recipe_c = FujifilmRecipeFactory()
        client.post("/recipes/delete/", {"recipe_ids": [recipe_a.pk, recipe_b.pk]})
        assert not models.FujifilmRecipe.objects.filter(pk__in=[recipe_a.pk, recipe_b.pk]).exists()
        assert models.FujifilmRecipe.objects.filter(pk=recipe_c.pk).exists()

    def test_response_shows_removed_count(self, client) -> None:
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        response = client.post("/recipes/delete/", {"recipe_ids": [recipe_a.pk, recipe_b.pk]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert "2 recipe" in soup.get_text().lower()

    def test_response_marks_all_succeeded_when_all_deleted(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.post("/recipes/delete/", {"recipe_ids": [recipe.pk]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "true"}) is not None

    def test_empty_ids_returns_200(self, client) -> None:
        response = client.post("/recipes/delete/", {})
        assert response.status_code == 200

    def test_empty_ids_marks_all_succeeded(self, client) -> None:
        response = client.post("/recipes/delete/", {})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "true"}) is not None


@pytest.mark.django_db
class TestRemoveRecipesViewFailure:
    def test_not_found_id_shows_not_found_message(self, client) -> None:
        response = client.post("/recipes/delete/", {"recipe_ids": [99999]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert "not found" in soup.get_text().lower()

    def test_not_found_marks_not_all_succeeded(self, client) -> None:
        response = client.post("/recipes/delete/", {"recipe_ids": [99999]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None

    def test_recipe_with_images_is_not_deleted(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        client.post("/recipes/delete/", {"recipe_ids": [recipe.pk]})
        assert models.FujifilmRecipe.objects.filter(pk=recipe.pk).exists()

    def test_response_shows_recipe_name_for_has_images_failure(self, client) -> None:
        recipe = FujifilmRecipeFactory(name="Velvia")
        ImageFactory(fujifilm_recipe=recipe)
        response = client.post("/recipes/delete/", {"recipe_ids": [recipe.pk]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Velvia" in soup.get_text()
        assert "images" in soup.get_text().lower()

    def test_partial_failure_marks_not_all_succeeded(self, client) -> None:
        recipe_ok = FujifilmRecipeFactory()
        recipe_with_image = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_with_image)
        response = client.post("/recipes/delete/", {
            "recipe_ids": [recipe_ok.pk, recipe_with_image.pk],
        })
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None

    def test_partial_failure_still_deletes_successful_recipe(self, client) -> None:
        recipe_ok = FujifilmRecipeFactory()
        recipe_with_image = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_with_image)
        client.post("/recipes/delete/", {
            "recipe_ids": [recipe_ok.pk, recipe_with_image.pk],
        })
        assert not models.FujifilmRecipe.objects.filter(pk=recipe_ok.pk).exists()
        assert models.FujifilmRecipe.objects.filter(pk=recipe_with_image.pk).exists()

    def test_unexpected_exception_shows_error_message(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        with patch(
            "src.interfaces.recipes.views.remove_recipes_uc.remove_recipes",
            side_effect=RuntimeError("boom"),
        ):
            response = client.post("/recipes/delete/", {"recipe_ids": [recipe.pk]})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "unexpected" in soup.get_text().lower()
