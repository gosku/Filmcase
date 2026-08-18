import json

import attrs
import pytest

from src.domain.images import dataclasses as image_dataclasses
from src.domain.recipes import queries as recipe_queries
from tests.factories import FujifilmRecipeFactory


def _recipe(**kwargs):
    return FujifilmRecipeFactory(sharpness=0, high_iso_nr=0, clarity=0, **kwargs)


def _url(recipe_id: int) -> str:
    return f"/recipes/{recipe_id}/camera-payload.json"


@pytest.mark.django_db
class TestRecipeCameraPayloadView:
    def test_serves_the_recipe_as_json(self, client):
        recipe = _recipe(name="Kodak Portra")

        response = client.get(_url(recipe.id))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"
        assert json.loads(response.content)["name"] == "Kodak Portra"

    def test_keys_are_the_domain_object_fields_one_for_one(self, client):
        # The client deserializes straight into its own port of
        # FujifilmRecipeData, so the shapes have to stay in step.
        recipe = _recipe(name="One For One")

        payload = json.loads(client.get(_url(recipe.id)).content)

        expected = {f.name for f in attrs.fields(image_dataclasses.FujifilmRecipeData)}
        assert set(payload) == expected

    def test_matches_what_the_server_side_push_would_convert(self, client):
        # Both transports have to start from the same domain object; this is the
        # assertion that says so.
        recipe = _recipe(name="Same Source")

        payload = json.loads(client.get(_url(recipe.id)).content)

        expected = attrs.asdict(recipe_queries.recipe_from_db(recipe=recipe))
        assert payload == json.loads(json.dumps(expected))

    def test_applies_normalization(self, client):
        # A monochrome recipe has no colour, and normalization is what nulls it.
        # If the endpoint skipped that step the client would write a colour value
        # the server-side path never would.
        recipe = _recipe(name="Acros Mono", film_simulation="Acros")

        payload = json.loads(client.get(_url(recipe.id)).content)

        assert payload["color"] is None

    def test_absent_optional_fields_are_null(self, client):
        recipe = _recipe(name="No Grain Size", grain_roughness="Off", grain_size="")

        payload = json.loads(client.get(_url(recipe.id)).content)

        assert payload["grain_size"] is None

    def test_unknown_recipe_returns_404(self, client):
        assert client.get(_url(999_999)).status_code == 404

    def test_unnamed_recipe_returns_404(self, client):
        # Mirrors SelectSlot: a recipe with no name cannot be written to a slot.
        recipe = _recipe(name="")

        assert client.get(_url(recipe.id)).status_code == 404

    def test_is_not_cached(self, client):
        recipe = _recipe(name="Fresh Each Time")

        response = client.get(_url(recipe.id))

        assert response["Cache-Control"] == "no-store"

    def test_needs_no_camera_attached(self, client, settings):
        settings.PTP_DEVICE = None
        recipe = _recipe(name="No Camera Here")

        assert client.get(_url(recipe.id)).status_code == 200
