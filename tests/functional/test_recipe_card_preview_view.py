import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestRecipeCardPreview:
    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/preview/")
        assert response.status_code == 200

    def test_renders_preview_image_tag(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/preview/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("img", class_="card-result-image") is not None

    def test_preview_image_src_points_to_preview_file_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/preview/")
        soup = BeautifulSoup(response.content, "html.parser")
        img = soup.find("img", class_="card-result-image")
        assert img["src"].startswith(f"/recipes/{recipe.pk}/card/preview/file/")

    def test_nonexistent_recipe_returns_error_partial(self, client):
        response = client.get("/recipes/99999/card/partial/preview/")
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="card-result-error") is not None

    def test_label_style_param_is_forwarded_to_preview_file_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/preview/?label_style=short")
        soup = BeautifulSoup(response.content, "html.parser")
        img = soup.find("img", class_="card-result-image")
        assert "label_style=short" in img["src"]

    def test_label_style_defaults_to_long(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/preview/")
        soup = BeautifulSoup(response.content, "html.parser")
        img = soup.find("img", class_="card-result-image")
        assert "label_style=long" in img["src"]
