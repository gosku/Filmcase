from __future__ import annotations

from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.application.usecases.recipes import update_recipe_manually as update_recipe_manually_uc
from src.data import models
from src.domain.recipes import operations as recipe_operations
from src.domain.images import dataclasses as image_dataclasses
from tests.factories import FujifilmRecipeFactory, ImageFactory


def _url(recipe_id: int) -> str:
    return f"/recipes/{recipe_id}/edit/"


def _valid_data(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Updated Recipe",
        "film_simulation": "Velvia",
        "dynamic_range": "DR100",
        "d_range_priority": "Off",
        "grain_roughness": "Off",
        "grain_size": "Off",
        "color_chrome_effect": "Off",
        "color_chrome_fx_blue": "Off",
        "white_balance": "Auto",
        "white_balance_red": "0",
        "white_balance_blue": "0",
        "highlight": "0",
        "shadow": "0",
        "color": "0",
        "sharpness": "0",
        "high_iso_nr": "0",
        "clarity": "0",
    }
    base.update(overrides)
    return base


@pytest.mark.django_db
class TestEditRecipeViewGet:
    def test_get_returns_200(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.get(_url(recipe.pk))
        assert response.status_code == 200

    def test_get_returns_404_for_nonexistent_recipe(self, client) -> None:
        response = client.get(_url(99999))
        assert response.status_code == 404

    def test_get_renders_form_in_context(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.get(_url(recipe.pk))
        assert "form" in response.context

    def test_get_populates_film_simulation_initial(self, client) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Velvia")
        response = client.get(_url(recipe.pk))
        form = response.context["form"]
        assert form.initial["film_simulation"] == "Velvia"

    def test_get_populates_name_initial(self, client) -> None:
        recipe = FujifilmRecipeFactory(name="My Velvia")
        response = client.get(_url(recipe.pk))
        form = response.context["form"]
        assert form.initial["name"] == "My Velvia"

    def test_get_populates_white_balance_initial(self, client) -> None:
        recipe = FujifilmRecipeFactory(white_balance="Daylight")
        response = client.get(_url(recipe.pk))
        form = response.context["form"]
        assert form.initial["white_balance"] == "Daylight"

    def test_get_parses_kelvin_white_balance_initial(self, client) -> None:
        recipe = FujifilmRecipeFactory(white_balance="6500K")
        response = client.get(_url(recipe.pk))
        form = response.context["form"]
        assert form.initial["white_balance"] == "Kelvin"
        assert form.initial["kelvin_temperature"] == 6500


@pytest.mark.django_db
class TestEditRecipeViewPost:
    def test_valid_post_redirects(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.post(_url(recipe.pk), _valid_data())
        assert response.status_code == 302

    def test_valid_post_updates_recipe_in_db(self, client) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Velvia"

    def test_valid_post_redirects_to_recipe_detail(self, client) -> None:
        recipe = FujifilmRecipeFactory(name="My Recipe")
        response = client.post(_url(recipe.pk), _valid_data(name="My Recipe"))
        assert response.status_code == 302
        assert response["Location"] == f"/recipes/{recipe.pk}/?name_search=My+Recipe"

    def test_post_without_name_shows_error(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        data = _valid_data()
        del data["name"]
        form = client.post(_url(recipe.pk), data).context["form"]
        assert "name" in form.errors

    def test_post_with_invalid_field_shows_error(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        form = client.post(_url(recipe.pk), _valid_data(color="5")).context["form"]
        assert "color" in form.errors


@pytest.mark.django_db
class TestEditRecipeViewHasImages:
    def test_get_includes_is_settings_editable_false_when_recipe_has_images(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        response = client.get(_url(recipe.pk))
        assert response.context["is_settings_editable"] is False

    def test_get_includes_is_settings_editable_true_when_recipe_has_no_images(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.get(_url(recipe.pk))
        assert response.context["is_settings_editable"] is True

    def test_post_settings_change_when_recipe_has_images_returns_200(self, client) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        response = client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        assert response.status_code == 200

    def test_post_settings_change_when_recipe_has_images_shows_error(self, client) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        response = client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        errors = response.context["form"].non_field_errors()
        assert any("cannot be changed" in e.lower() for e in errors)

    def test_post_settings_change_when_recipe_has_images_does_not_update_recipe(self, client) -> None:
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory(fujifilm_recipe=recipe)
        client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        recipe.refresh_from_db()
        assert recipe.film_simulation == "Provia"

    def test_post_name_only_change_when_recipe_has_images_redirects(self, client) -> None:
        from decimal import Decimal
        # Recipe must have explicit decimal values so the injected form data matches exactly.
        recipe = FujifilmRecipeFactory(
            name="Old Name",
            film_simulation="Provia",
            dynamic_range="DR100",
            d_range_priority="Off",
            grain_roughness="Off",
            grain_size="Off",
            color_chrome_effect="Off",
            color_chrome_fx_blue="Off",
            white_balance="Auto",
            white_balance_red=0,
            white_balance_blue=0,
            highlight=Decimal("0"),
            shadow=Decimal("0"),
            color=0,
            sharpness=0,
            high_iso_nr=0,
            clarity=0,
        )
        ImageFactory(fujifilm_recipe=recipe)
        response = client.post(_url(recipe.pk), _valid_data(film_simulation="Provia", name="New Name"))
        assert response.status_code == 302

    def test_post_name_only_change_when_recipe_has_images_updates_name(self, client) -> None:
        from decimal import Decimal
        recipe = FujifilmRecipeFactory(
            name="Old Name",
            film_simulation="Provia",
            dynamic_range="DR100",
            d_range_priority="Off",
            grain_roughness="Off",
            grain_size="Off",
            color_chrome_effect="Off",
            color_chrome_fx_blue="Off",
            white_balance="Auto",
            white_balance_red=0,
            white_balance_blue=0,
            highlight=Decimal("0"),
            shadow=Decimal("0"),
            color=0,
            sharpness=0,
            high_iso_nr=0,
            clarity=0,
        )
        ImageFactory(fujifilm_recipe=recipe)
        client.post(_url(recipe.pk), _valid_data(film_simulation="Provia", name="New Name"))
        recipe.refresh_from_db()
        assert recipe.name == "New Name"

    def _make_conflicting_existing_recipe(self) -> None:
        """Create a recipe with the exact settings _valid_data(film_simulation="Velvia") would produce."""
        recipe_operations.get_or_create_recipe_from_data(
            data=image_dataclasses.FujifilmRecipeData(
                film_simulation="Velvia",
                d_range_priority="Off",
                grain_roughness="Off",
                color_chrome_effect="Off",
                color_chrome_fx_blue="Off",
                white_balance="Auto",
                white_balance_red=0,
                white_balance_blue=0,
                sharpness="0",
                high_iso_nr="0",
                clarity="0",
                dynamic_range="DR100",
                highlight="0",
                shadow="0",
                color="0",
            )
        )

    def test_post_when_settings_match_existing_recipe_returns_200(self, client) -> None:
        self._make_conflicting_existing_recipe()
        recipe = FujifilmRecipeFactory(white_balance_red=99)
        response = client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        assert response.status_code == 200

    def test_post_when_settings_match_existing_recipe_shows_already_exists_error(self, client) -> None:
        self._make_conflicting_existing_recipe()
        recipe = FujifilmRecipeFactory(white_balance_red=99)
        response = client.post(_url(recipe.pk), _valid_data(film_simulation="Velvia"))
        errors = response.context["form"].non_field_errors()
        assert any("already exists" in e.lower() for e in errors)

    def test_unexpected_error_shows_generic_message(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        with patch.object(
            update_recipe_manually_uc, "update_recipe_manually", side_effect=RuntimeError("boom")
        ):
            response = client.post(_url(recipe.pk), _valid_data())
        assert response.status_code == 200
        errors = response.context["form"].non_field_errors()
        assert any("unexpected error" in e.lower() for e in errors)


@pytest.mark.django_db
class TestEditRecipeNoticeBanner:
    def _create_version_link(self, client, recipe):
        response = client.get(_url(recipe.pk))
        soup = BeautifulSoup(response.content, "html.parser")
        return soup.find("a", href=f"/recipes/{recipe.pk}/create-version/")

    def test_notice_banner_absent_when_recipe_has_no_images(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        assert self._create_version_link(client, recipe) is None

    def test_notice_banner_contains_create_version_link_when_recipe_has_images(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe)
        assert self._create_version_link(client, recipe) is not None
