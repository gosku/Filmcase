import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestSetRecipeCoverImageView:
    def test_returns_404_for_nonexistent_recipe(self, client):
        image = ImageFactory()
        response = client.post(f"/recipes/99999/set-cover-image/{image.id}/")
        assert response.status_code == 404

    def test_returns_404_for_nonexistent_image(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.post(f"/recipes/{recipe.id}/set-cover-image/99999/")
        assert response.status_code == 404

    def test_returns_404_when_image_not_associated_to_recipe(self, client):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe_b)

        response = client.post(f"/recipes/{recipe_a.id}/set-cover-image/{image.id}/")

        assert response.status_code == 404

    def test_happy_path_sets_cover_image_in_db(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        client.post(f"/recipes/{recipe.id}/set-cover-image/{image.id}/")

        recipe.refresh_from_db()
        assert recipe.cover_image_id == image.pk

    def test_happy_path_returns_200(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = client.post(f"/recipes/{recipe.id}/set-cover-image/{image.id}/")

        assert response.status_code == 200

    def test_happy_path_response_shows_cover_image_badge(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = client.post(f"/recipes/{recipe.id}/set-cover-image/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="cover-image-badge") is not None

    def test_happy_path_response_does_not_show_set_cover_button(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = client.post(f"/recipes/{recipe.id}/set-cover-image/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="set-cover-btn") is None

    def test_get_method_not_allowed(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = client.get(f"/recipes/{recipe.id}/set-cover-image/{image.id}/")

        assert response.status_code == 405


@pytest.mark.django_db
class TestSetCoverImageButtonInImageDetail:
    def _get_partial(self, client, image_id):
        return client.get(f"/images/{image_id}/", HTTP_HX_REQUEST="true")

    def test_set_cover_button_present_when_image_has_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="set-cover-btn") is not None

    def test_set_cover_button_absent_when_image_has_no_recipe(self, client):
        image = ImageFactory(fujifilm_recipe=None)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="set-cover-btn") is None

    def test_set_cover_button_posts_to_correct_url(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="set-cover-btn")
        assert btn is not None
        assert btn["hx-post"] == f"/recipes/{recipe.id}/set-cover-image/{image.id}/"

    def test_set_cover_button_wrapper_has_correct_id(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        wrapper = soup.find(id=f"cover-image-btn-{image.id}")
        assert wrapper is not None
        assert wrapper.find(class_="set-cover-btn") is not None
