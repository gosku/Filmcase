import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRecipeCardModalView:
    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        assert response.status_code == 200

    def test_returns_404_for_missing_recipe(self, client):
        response = client.get("/recipes/99999/card/partial/modal/")
        assert response.status_code == 404

    def test_renders_recipe_name_when_set(self, client):
        recipe = FujifilmRecipeFactory(name="Autumn Velvia")
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Autumn Velvia" in soup.get_text()

    def test_renders_film_simulation_when_no_name(self, client):
        recipe = FujifilmRecipeFactory(name="", film_simulation="Classic Chrome")
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Classic Chrome" in soup.get_text()

    def test_renders_image_thumbnails_when_images_exist(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("input", {"type": "radio", "value": str(image.pk)}) is not None

    def test_renders_gradient_option_alongside_images(self, client):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("input", {"type": "radio", "name": "image_id", "value": ""}) is not None

    def test_image_gallery_section_absent_when_no_images(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="card-image-gallery") is None

    def test_create_button_posts_to_create_recipe_card_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="card-create-btn")
        assert btn is not None
        assert btn.get("hx-post") == f"/recipes/{recipe.pk}/card/partial/create/"

    def test_preview_pane_fetches_from_preview_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/partial/modal/")
        soup = BeautifulSoup(response.content, "html.parser")
        pane = soup.find(id="card-preview-pane")
        assert pane is not None
        assert pane.get("hx-get") == f"/recipes/{recipe.pk}/card/partial/preview/"


@pytest.mark.django_db
class TestCreateRecipeCardButtonInRecipeDetail:
    def test_recipe_detail_has_create_recipe_card_button(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/", HTTP_HX_REQUEST="true")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"hx-get": f"/recipes/{recipe.pk}/card/partial/modal/"}) is not None

    def test_create_recipe_card_button_targets_card_overlay(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/", HTTP_HX_REQUEST="true")
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(attrs={"hx-get": f"/recipes/{recipe.pk}/card/partial/modal/"})
        assert btn["hx-target"] == "#card-overlay"

    def test_recipe_detail_has_card_overlay_div(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/", HTTP_HX_REQUEST="true")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="card-overlay") is not None
