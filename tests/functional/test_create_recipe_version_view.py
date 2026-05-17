from __future__ import annotations

from decimal import Decimal

import pytest

from src.data import models
from tests.factories import FujifilmRecipeFactory, RecipeGroupFactory, RecipeGroupMemberFactory


def _url(recipe_id: int) -> str:
    return f"/recipes/{recipe_id}/create-version/"


def _valid_data(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "My Recipe v2",
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


def _source_in_group() -> tuple[models.FujifilmRecipe, models.RecipeGroup]:
    group = RecipeGroupFactory()
    source = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0)
    RecipeGroupMemberFactory(recipe=source, group=group, position=1)
    return source, group


@pytest.mark.django_db
class TestCreateRecipeVersionViewGet:
    def test_returns_400_when_recipe_has_no_version_line_member(self, client) -> None:
        recipe = FujifilmRecipeFactory()
        response = client.get(_url(recipe.pk))
        assert response.status_code == 400

    def test_returns_404_for_nonexistent_recipe_id(self, client) -> None:
        response = client.get(_url(99999))
        assert response.status_code == 404

    def test_returns_200_when_recipe_has_version_line(self, client) -> None:
        source, _ = _source_in_group()
        response = client.get(_url(source.pk))
        assert response.status_code == 200

    def test_form_is_prepopulated_with_film_simulation(self, client) -> None:
        source, _ = _source_in_group()
        response = client.get(_url(source.pk))
        assert response.context["form"].initial["film_simulation"] == "Provia"

    def test_form_is_prepopulated_with_name(self, client) -> None:
        group = RecipeGroupFactory()
        source = FujifilmRecipeFactory(name="Summer Preset", white_balance_red=0)
        RecipeGroupMemberFactory(recipe=source, group=group, position=1)
        response = client.get(_url(source.pk))
        assert response.context["form"].initial["name"] == "Summer Preset"

    def test_form_parses_kelvin_white_balance(self, client) -> None:
        group = RecipeGroupFactory()
        source = FujifilmRecipeFactory(white_balance="6500K", white_balance_red=0)
        RecipeGroupMemberFactory(recipe=source, group=group, position=1)
        response = client.get(_url(source.pk))
        form = response.context["form"]
        assert form.initial["white_balance"] == "Kelvin"
        assert form.initial["kelvin_temperature"] == 6500


@pytest.mark.django_db
class TestCreateRecipeVersionViewPost:
    def test_new_recipe_belongs_to_same_group_as_source(self, client) -> None:
        source, group = _source_in_group()
        client.post(_url(source.pk), _valid_data())
        assert models.RecipeGroupMember.objects.filter(group=group).count() == 2

    def test_new_recipe_has_latest_position_in_group(self, client) -> None:
        source, group = _source_in_group()
        client.post(_url(source.pk), _valid_data())
        new_recipe = models.FujifilmRecipe.objects.exclude(pk=source.pk).get()
        member = models.RecipeGroupMember.objects.get(recipe=new_recipe)
        assert member.position == 2

    def test_valid_post_redirects_to_new_recipe_detail(self, client) -> None:
        source, _ = _source_in_group()
        response = client.post(_url(source.pk), _valid_data(name="V2"))
        new_recipe = models.FujifilmRecipe.objects.exclude(pk=source.pk).get()
        assert response.status_code == 302
        assert response["Location"] == f"/recipes/{new_recipe.pk}/?name_search=V2"

    def test_duplicate_settings_show_already_exists_error(self, client) -> None:
        source, group = _source_in_group()
        existing = FujifilmRecipeFactory(
            film_simulation="Velvia",
            white_balance_red=0,
            white_balance_blue=0,
            highlight=Decimal("0"),
            shadow=Decimal("0"),
            color=Decimal("0"),
            sharpness=Decimal("0"),
            high_iso_nr=Decimal("0"),
            clarity=Decimal("0"),
        )
        RecipeGroupMemberFactory(recipe=existing, group=RecipeGroupFactory(), position=1)
        response = client.post(_url(source.pk), _valid_data())
        assert response.status_code == 200
        errors = response.context["form"].non_field_errors()
        assert any("already exists" in e for e in errors)
