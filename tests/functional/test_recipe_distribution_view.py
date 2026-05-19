import pytest
from bs4 import BeautifulSoup

from tests.factories import (
    FujifilmRecipeFactory,
    RecipeGroupFactory,
    RecipeGroupMemberFactory,
)


def _make_version_line(*recipes):
    group = RecipeGroupFactory()
    for i, recipe in enumerate(recipes, start=1):
        RecipeGroupMemberFactory(group=group, recipe=recipe, position=i)
    return group


@pytest.mark.django_db
class TestRecipeDistributionView:
    def _get(self, client, recipe_id, **params):
        url = f"/recipes/{recipe_id}/distribution/"
        if params:
            query = "&".join(f"{k}={v}" for k, v in params.items())
            url = f"{url}?{query}"
        return client.get(url)

    def test_returns_200_for_existing_recipe_in_version_line(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk)

        assert response.status_code == 200

    def test_returns_200_for_scale_week(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk, scale="week")

        assert response.status_code == 200

    def test_returns_200_for_scale_year(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk, scale="year")

        assert response.status_code == 200

    def test_returns_404_for_non_existent_recipe(self, client):
        response = self._get(client, 99999)

        assert response.status_code == 404

    def test_returns_400_for_invalid_scale_value(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk, scale="daily")

        assert response.status_code == 400

    def test_returns_400_when_recipe_has_no_version_group(self, client):
        recipe = FujifilmRecipeFactory()

        response = self._get(client, recipe.pk)

        assert response.status_code == 400

    def test_response_does_not_include_doctype(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk)

        assert b"<!DOCTYPE" not in response.content

    def test_renders_distribution_and_versions_header(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")

        assert "DISTRIBUTION" in soup.get_text().upper()
        assert "VERSIONS" in soup.get_text().upper()

    def test_renders_one_stat_row_per_version(self, client):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        recipe_v3 = FujifilmRecipeFactory()
        _make_version_line(recipe_v1, recipe_v2, recipe_v3)

        response = self._get(client, recipe_v2.pk)
        soup = BeautifulSoup(response.content, "html.parser")

        rows = soup.find_all(class_="dist-stat-row")
        assert len(rows) == 3

    def test_active_scale_month_button_has_is_active_class_by_default(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")

        active_btn = soup.find(class_=lambda c: c and "dist-scale-btn" in c and "is-active" in c)
        assert active_btn is not None
        assert active_btn.get_text(strip=True) == "M"

    def test_active_scale_week_button_has_is_active_class_when_scale_is_week(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk, scale="week")
        soup = BeautifulSoup(response.content, "html.parser")

        active_btn = soup.find(class_=lambda c: c and "dist-scale-btn" in c and "is-active" in c)
        assert active_btn is not None
        assert active_btn.get_text(strip=True) == "W"

    def test_scale_buttons_target_closest_detail_distribution(self, client):
        recipe = FujifilmRecipeFactory()
        _make_version_line(recipe)

        response = self._get(client, recipe.pk)
        soup = BeautifulSoup(response.content, "html.parser")

        scale_buttons = soup.find_all(class_="dist-scale-btn")
        for btn in scale_buttons:
            assert btn.get("hx-target") == "closest .detail-distribution"

    def test_now_chip_is_shown_for_the_requested_recipe(self, client):
        recipe_v1 = FujifilmRecipeFactory()
        recipe_v2 = FujifilmRecipeFactory()
        _make_version_line(recipe_v1, recipe_v2)

        response = self._get(client, recipe_v2.pk)
        soup = BeautifulSoup(response.content, "html.parser")

        now_chips = soup.find_all(class_="dist-stat-now")
        assert len(now_chips) == 1
