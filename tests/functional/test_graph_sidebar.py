import json

import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory, ImageFactory

_DEFAULT_SIM = "Provia"


def _recipe(**kwargs):
    defaults = {
        "film_simulation": _DEFAULT_SIM,
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


def _soup(response):
    return BeautifulSoup(response.content, "html.parser")


def _rows(response):
    return _soup(response).find_all(class_="graph-recipe-list__row")


def _row_names(response):
    return [row.find(class_="graph-recipe-list__name").get_text(strip=True) for row in _rows(response)]


def _row_uses(response):
    return [row.find(class_="graph-recipe-list__uses").get_text(strip=True) for row in _rows(response)]


@pytest.mark.django_db
class TestGraphSidebarRecipeList:
    def test_every_graph_node_has_a_row(self, client):
        _recipe(name="One", grain_roughness="Off")
        _recipe(name="Two", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert len(_rows(response)) == 2

    def test_rows_are_ordered_most_used_first(self, client):
        quiet = _recipe(name="Quiet", grain_roughness="Off")
        busy = _recipe(name="Busy", grain_roughness="Strong")
        ImageFactory.create_batch(2, fujifilm_recipe=quiet)
        ImageFactory.create_batch(7, fujifilm_recipe=busy)

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert _row_names(response) == ["Busy", "Quiet"]

    def test_use_counts_are_grouped_with_separators(self, client):
        recipe = _recipe(name="Busy")
        ImageFactory.create_batch(4, fujifilm_recipe=recipe)

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert _row_uses(response) == ["4"]

    def test_rows_carry_the_recipe_id_for_selection(self, client):
        recipe = _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert _rows(response)[0]["data-recipe-id"] == str(recipe.pk)

    def test_the_reference_row_is_marked(self, client):
        root = _recipe(name="Root")
        ImageFactory.create_batch(5, fujifilm_recipe=root)
        _recipe(name="Other", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        marked = [
            row.find(class_="graph-recipe-list__name").get_text(strip=True)
            for row in _rows(response)
            if "graph-recipe-list__row--reference" in row.get("class", [])
        ]
        assert marked == ["Root"]

    def test_named_and_unnamed_rows_look_the_same(self, client):
        # Showing all recipes means treating them all as equally important; the
        # only rows that stand out are the reference and the compared one.
        _recipe(name="Named", grain_roughness="Off")
        _recipe(name="", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        classes = {
            tuple(row.find(class_="graph-recipe-list__name").get("class", []))
            for row in _rows(response)
            if "graph-recipe-list__row--reference" not in row.get("class", [])
        }
        assert classes == {("graph-recipe-list__name",)}

    def test_the_count_label_reflects_the_number_of_rows(self, client):
        _recipe(name="One", grain_roughness="Off")
        _recipe(name="Two", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert "2" in _soup(response).find(class_="graph-sidebar__count").get_text()

    def test_per_recipe_page_also_renders_the_list(self, client):
        root = _recipe(name="Root", grain_roughness="Off")
        _recipe(name="Near", grain_roughness="Strong")

        response = client.get(f"/recipes/graph/{root.pk}/")

        assert len(_rows(response)) == 2


@pytest.mark.django_db
class TestGraphSidebarNamedFilterControl:
    def test_it_is_a_single_on_off_switch(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        toggle = _soup(response).find(id="named-only-toggle")
        assert toggle is not None
        assert toggle["type"] == "checkbox"

    def test_it_is_off_by_default(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert not _soup(response).find(id="named-only-toggle").has_attr("checked")

    def test_it_is_on_when_the_filter_is_applied(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM, "named": "1"})

        assert _soup(response).find(id="named-only-toggle").has_attr("checked")

    def test_the_switch_is_labelled(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        label = _soup(response).find("label", attrs={"for": "named-only-toggle"})
        assert "Named recipes only" in label.get_text()

    def test_filtering_removes_unnamed_rows(self, client):
        _recipe(name="Named", grain_roughness="Off")
        _recipe(name="", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM, "named": "1"})

        assert _row_names(response) == ["Named"]


@pytest.mark.django_db
class TestGraphSidebarLegend:
    def test_legend_starts_without_a_comparison(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        legend = _soup(response).find(class_="graph-legend")
        assert "graph-legend--no-comparison" in legend.get("class", [])

    def test_legend_offers_both_compare_states(self, client):
        _recipe(name="One")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        legend = _soup(response).find(class_="graph-legend")
        assert legend.find(class_="graph-legend__row--compared") is not None
        assert legend.find(class_="graph-legend__row--pick") is not None


@pytest.mark.django_db
class TestGraphSidebarIsReRenderedForFilterChanges:
    def test_json_response_carries_the_rendered_sidebar(self, client):
        _recipe(name="One")

        response = client.get(
            "/recipes/graph/", {"film_sim": _DEFAULT_SIM}, HTTP_ACCEPT="application/json",
        )

        data = json.loads(response.content)
        assert "graph-recipe-list" in data["sidebar_html"]

    def test_json_sidebar_reflects_the_named_filter(self, client):
        _recipe(name="Named", grain_roughness="Off")
        _recipe(name="", grain_roughness="Strong")

        response = client.get(
            "/recipes/graph/",
            {"film_sim": _DEFAULT_SIM, "named": "1"},
            HTTP_ACCEPT="application/json",
        )

        data = json.loads(response.content)
        assert data["sidebar_html"].count("data-recipe-id") == 1

    def test_per_recipe_json_response_carries_the_sidebar(self, client):
        root = _recipe(name="Root")

        response = client.get(f"/recipes/graph/{root.pk}/", HTTP_ACCEPT="application/json")

        data = json.loads(response.content)
        assert "graph-recipe-list" in data["sidebar_html"]
