import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRecipeDetailView:
    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/")
        assert response.status_code == 200

    def test_returns_404_for_missing_recipe(self, client):
        response = client.get("/recipes/99999/")
        assert response.status_code == 404

    def test_shows_recipe_name_in_page(self, client):
        recipe = FujifilmRecipeFactory(name="Fuji Street Look")
        response = client.get(f"/recipes/{recipe.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Fuji Street Look" in soup.get_text()

    def test_shows_film_simulation_in_page(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Classic Chrome")
        response = client.get(f"/recipes/{recipe.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Classic Chrome" in soup.get_text()

    def test_shows_close_button_linking_to_explorer(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")
        close_btn = soup.find(class_="detail-close")
        assert close_btn is not None
        assert close_btn["href"] == "/recipes/"

    def test_close_button_is_in_header(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")
        header = soup.find(class_="detail-header")
        assert header is not None
        assert header.find(class_="detail-close") is not None

    def test_shows_recipe_settings_in_page(self, client):
        recipe = FujifilmRecipeFactory(
            grain_roughness="Strong",
            grain_size="Large",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Weak",
        )
        response = client.get(f"/recipes/{recipe.pk}/")
        soup = BeautifulSoup(response.content, "html.parser")
        text = soup.get_text()
        assert "Strong" in text
        assert "Large" in text
        assert "Weak" in text


@pytest.mark.django_db
class TestRecipeDetailMonochromaticFields:
    def _get_partial(self, client, recipe_id):
        return client.get(f"/recipes/{recipe_id}/", HTTP_HX_REQUEST="true")

    def test_monochromatic_fields_shown_for_monochromatic_film_simulation(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Acros STD")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        text = soup.get_text()
        assert "BW Warm" in text
        assert "BW Magenta" in text

    def test_monochromatic_fields_hidden_for_colour_film_simulation(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        text = soup.get_text()
        assert "BW Warm" not in text
        assert "BW Magenta" not in text


@pytest.mark.django_db
class TestRecipeDetailPartial:
    def _get_partial(self, client, recipe_id):
        return client.get(f"/recipes/{recipe_id}/", HTTP_HX_REQUEST="true")

    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        response = self._get_partial(client, recipe.pk)
        assert response.status_code == 200

    def test_returns_404_for_missing_recipe(self, client):
        response = client.get("/recipes/99999/", HTTP_HX_REQUEST="true")
        assert response.status_code == 404

    def test_partial_does_not_include_html_doctype(self, client):
        recipe = FujifilmRecipeFactory()
        response = self._get_partial(client, recipe.pk)
        assert b"<!DOCTYPE" not in response.content

    def test_shows_recipe_name_in_partial(self, client):
        recipe = FujifilmRecipeFactory(name="Street Provia")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Street Provia" in soup.get_text()

    def test_shows_film_simulation_in_partial(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Velvia")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        assert "Velvia" in soup.get_text()

    def test_close_button_present_in_partial(self, client):
        recipe = FujifilmRecipeFactory()
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="detail-close") is not None

    def test_send_to_camera_button_present_when_recipe_named(self, client):
        recipe = FujifilmRecipeFactory(name="Cuban Negative")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="send-to-camera-btn")
        assert btn is not None
        assert btn.get("hx-get") == f"/recipes/{recipe.pk}/push/"

    def test_send_to_camera_button_absent_when_recipe_unnamed(self, client):
        recipe = FujifilmRecipeFactory(name="")
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="send-to-camera-btn") is None

    def test_shows_detail_overlay_structure(self, client):
        recipe = FujifilmRecipeFactory()
        response = self._get_partial(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="detail-overlay") is not None
        assert soup.find(class_="detail-header") is not None
        assert soup.find(class_="detail-settings-col") is not None
        assert soup.find(class_="detail-actions-col") is not None


@pytest.mark.django_db
class TestRecipeCardHtmxAttributes:
    def test_recipe_card_has_hx_get_pointing_to_detail_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        card = soup.find(class_="recipe-card")
        assert card is not None
        assert card.get("hx-get") == f"/recipes/{recipe.pk}/"

    def test_recipe_card_targets_recipe_detail_overlay(self, client):
        FujifilmRecipeFactory()
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        card = soup.find(class_="recipe-card")
        assert card.get("hx-target") == "#recipe-detail-overlay"

    def test_recipe_card_has_hx_push_url(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        card = soup.find(class_="recipe-card")
        assert card.get("hx-push-url") == f"/recipes/{recipe.pk}/"

    def test_explorer_page_has_recipe_detail_overlay_div(self, client):
        response = client.get("/recipes/")
        soup = BeautifulSoup(response.content, "html.parser")
        overlay = soup.find(id="recipe-detail-overlay")
        assert overlay is not None
        assert overlay.has_attr("hidden")
