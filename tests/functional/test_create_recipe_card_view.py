import pytest
from bs4 import BeautifulSoup

from src.data import models
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestCreateRecipeCard:
    def test_post_returns_200_for_existing_recipe(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        assert response.status_code == 200

    def test_post_returns_404_for_missing_recipe(self, client):
        response = client.post("/recipes/99999/card/partial/create/")
        assert response.status_code == 404

    def test_get_returns_405(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/create/")
        assert response.status_code == 405

    def test_post_saves_card_to_db(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        assert models.RecipeCard.objects.filter(recipe=recipe).exists()

    def test_response_includes_card_image(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("img", class_="card-result-image") is not None

    def test_card_image_src_points_to_file_view(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        soup = BeautifulSoup(response.content, "html.parser")
        img = soup.find("img", class_="card-result-image")
        card = models.RecipeCard.objects.get(recipe=recipe)
        assert img["src"] == f"/recipes/card/{card.pk}/file/"

    def test_response_shows_saved_confirmation(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="card-result-created") is not None

    def test_response_includes_download_link(self, client, tmp_path, settings):
        settings.RECIPE_CARDS_DIR = str(tmp_path)
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.pk}/card/partial/create/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="card-result-download") is not None
