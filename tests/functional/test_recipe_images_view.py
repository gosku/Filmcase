import json
from datetime import datetime, timezone

import pytest

from tests.factories import FujifilmRecipeFactory, ImageFactory


def _get(client, recipe_id):
    return client.get(f"/recipes/{recipe_id}/images/")


@pytest.mark.django_db
class TestRecipeImagesViewBasic:
    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()

        response = _get(client, recipe.pk)

        assert response.status_code == 200

    def test_returns_404_for_nonexistent_recipe(self, client):
        response = _get(client, 99999)

        assert response.status_code == 404

    def test_response_is_json(self, client):
        recipe = FujifilmRecipeFactory()

        response = _get(client, recipe.pk)

        assert response["Content-Type"] == "application/json"

    def test_response_has_images_key(self, client):
        recipe = FujifilmRecipeFactory()

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        assert "images" in data

    def test_empty_recipe_returns_empty_images_list(self, client):
        recipe = FujifilmRecipeFactory()

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        assert data["images"] == []


@pytest.mark.django_db
class TestRecipeImagesViewContent:
    def test_each_image_has_id_and_thumbnail_url(self, client):
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        assert len(data["images"]) == 1
        entry = data["images"][0]
        assert "id" in entry
        assert "thumbnail_url" in entry

    def test_thumbnail_url_contains_width_param(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        entry = next(e for e in data["images"] if e["id"] == image.pk)
        assert "width=600" in entry["thumbnail_url"]

    def test_thumbnail_url_references_correct_image_file_endpoint(self, client):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        entry = next(e for e in data["images"] if e["id"] == image.pk)
        assert f"/images/file/{image.pk}/" in entry["thumbnail_url"]

    def test_excludes_images_from_other_recipes(self, client):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        image_a = ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        response = _get(client, recipe_a.pk)

        data = json.loads(response.content)
        returned_ids = [e["id"] for e in data["images"]]
        assert returned_ids == [image_a.pk]


@pytest.mark.django_db
class TestRecipeImagesViewOrdering:
    def test_higher_rated_image_appears_first(self, client):
        recipe = FujifilmRecipeFactory()
        low = ImageFactory(fujifilm_recipe=recipe, rating=1)
        high = ImageFactory(fujifilm_recipe=recipe, rating=5)

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        ids = [e["id"] for e in data["images"]]
        assert ids.index(high.pk) < ids.index(low.pk)

    def test_same_rating_newer_image_appears_first(self, client):
        recipe = FujifilmRecipeFactory()
        older = ImageFactory(
            fujifilm_recipe=recipe,
            rating=3,
            taken_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        newer = ImageFactory(
            fujifilm_recipe=recipe,
            rating=3,
            taken_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )

        response = _get(client, recipe.pk)

        data = json.loads(response.content)
        ids = [e["id"] for e in data["images"]]
        assert ids.index(newer.pk) < ids.index(older.pk)
