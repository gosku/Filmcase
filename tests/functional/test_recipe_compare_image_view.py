import json

import pytest

from tests.factories import FujifilmRecipeFactory, ImageFactory


def _get(client, recipe_id, image_id):
    return client.get(f"/recipes/{recipe_id}/images/{image_id}/")


@pytest.mark.django_db
class TestRecipeCompareImageViewStatus:
    def test_returns_200_for_valid_recipe_and_image(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        assert response.status_code == 200

    def test_returns_404_for_nonexistent_recipe(self, client):
        image = ImageFactory()

        response = _get(client, 99999, image.pk)

        assert response.status_code == 404

    def test_returns_404_when_image_not_in_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        other_recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=other_recipe)

        response = _get(client, recipe.pk, image.pk)

        assert response.status_code == 404

    def test_returns_404_for_nonexistent_image(self, client):
        recipe = FujifilmRecipeFactory()

        response = _get(client, recipe.pk, 99999)

        assert response.status_code == 404

    def test_response_is_json(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        assert response["Content-Type"] == "application/json"


@pytest.mark.django_db
class TestRecipeCompareImageViewFields:
    def test_response_contains_id(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert data["id"] == image.pk

    def test_response_contains_thumbnail_url(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert "thumbnail_url" in data

    def test_response_contains_full_url(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert "full_url" in data

    def test_thumbnail_url_has_width_param(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert "width=600" in data["thumbnail_url"]

    def test_thumbnail_url_references_image_file_endpoint(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert f"/images/file/{image.pk}/" in data["thumbnail_url"]

    def test_full_url_references_image_file_endpoint_without_width(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert f"/images/file/{image.pk}/" in data["full_url"]
        assert "width" not in data["full_url"]


@pytest.mark.django_db
class TestRecipeCompareImageViewNavigation:
    def test_prev_id_is_none_for_first_image(self, client):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(fujifilm_recipe=recipe, rating=5)
        ImageFactory(fujifilm_recipe=recipe, rating=1)

        response = _get(client, recipe.pk, first.pk)

        data = json.loads(response.content)
        assert data["prev_id"] is None

    def test_next_id_is_set_for_first_image(self, client):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(fujifilm_recipe=recipe, rating=5)
        second = ImageFactory(fujifilm_recipe=recipe, rating=1)

        response = _get(client, recipe.pk, first.pk)

        data = json.loads(response.content)
        assert data["next_id"] == second.pk

    def test_next_id_is_none_for_last_image(self, client):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe, rating=5)
        last = ImageFactory(fujifilm_recipe=recipe, rating=1)

        response = _get(client, recipe.pk, last.pk)

        data = json.loads(response.content)
        assert data["next_id"] is None

    def test_prev_id_is_set_for_last_image(self, client):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(fujifilm_recipe=recipe, rating=5)
        last = ImageFactory(fujifilm_recipe=recipe, rating=1)

        response = _get(client, recipe.pk, last.pk)

        data = json.loads(response.content)
        assert data["prev_id"] == first.pk

    def test_both_prev_and_next_set_for_middle_image(self, client):
        recipe = FujifilmRecipeFactory()
        first = ImageFactory(fujifilm_recipe=recipe, rating=5)
        middle = ImageFactory(fujifilm_recipe=recipe, rating=3)
        last = ImageFactory(fujifilm_recipe=recipe, rating=1)

        response = _get(client, recipe.pk, middle.pk)

        data = json.loads(response.content)
        assert data["prev_id"] == first.pk
        assert data["next_id"] == last.pk

    def test_only_image_has_null_prev_and_next(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk, image.pk)

        data = json.loads(response.content)
        assert data["prev_id"] is None
        assert data["next_id"] is None
