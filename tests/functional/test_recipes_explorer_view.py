import json

import pytest

from tests.factories import FujifilmRecipeFactory, ImageFactory

_DEFAULT_SIM = "Provia"


def _get(client, **params):
    return client.get("/recipes/graph/", params)


def _get_json(client, **params):
    return client.get("/recipes/graph/", params, HTTP_ACCEPT="application/json")


def _elements(response):
    return json.loads(response.context["graph_elements_json"])


def _nodes(response):
    return [el for el in _elements(response) if "source" not in el["data"]]


def _edges(response):
    return [el for el in _elements(response) if "source" in el["data"]]


def _json_nodes(response):
    data = json.loads(response.content)
    return [el for el in data["elements"] if "source" not in el["data"]]


def _json_edges(response):
    data = json.loads(response.content)
    return [el for el in data["elements"] if "source" in el["data"]]


# ---------------------------------------------------------------------------
# Explorer (empty landing page)
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesExplorerView:
    def test_returns_200(self, client):
        response = client.get("/recipes/")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Graph page — basic rendering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesGraphView:
    def test_returns_200(self, client):
        response = _get(client, film_sim=_DEFAULT_SIM)
        assert response.status_code == 200

    def test_defaults_to_provia_without_film_sim_param(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        response = client.get("/recipes/graph/")

        assert response.context["active_film_simulation"] == "Provia"

    def test_empty_graph_when_no_recipes_for_film_sim(self, client):
        response = _get(client, film_sim="Provia")

        assert response.status_code == 200
        assert _nodes(response) == []
        assert _edges(response) == []

    def test_only_nodes_for_active_film_sim_are_returned(self, client):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get(client, film_sim="Provia")

        node_ids = {n["data"]["id"] for n in _nodes(response)}
        assert str(provia.pk) in node_ids
        assert str(velvia.pk) not in node_ids

    def test_node_data_includes_distance(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        node = _nodes(response)[0]
        assert "distance" in node["data"]

    def test_root_node_has_is_root_true(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        root_nodes = [n for n in _nodes(response) if n["data"].get("is_root")]
        assert len(root_nodes) == 1

    def test_node_data_includes_image_count(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = _get(client, film_sim="Provia")

        node = next(n for n in _nodes(response) if n["data"]["id"] == str(recipe.pk))
        assert node["data"]["image_count"] == 3

    def test_recipe_with_no_images_has_zero_image_count(self, client):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        node = next(n for n in _nodes(response) if n["data"]["id"] == str(recipe.pk))
        assert node["data"]["image_count"] == 0

    def test_named_recipe_uses_name_as_label(self, client):
        recipe = FujifilmRecipeFactory(name="Street Provia", film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        node = next(n for n in _nodes(response) if n["data"]["id"] == str(recipe.pk))
        assert node["data"]["label"] == "Street Provia"

    def test_unnamed_recipe_uses_id_prefix_as_label(self, client):
        recipe = FujifilmRecipeFactory(name="", film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        node = next(n for n in _nodes(response) if n["data"]["id"] == str(recipe.pk))
        assert node["data"]["label"] == f"#{recipe.pk}"

    def test_film_simulations_context_contains_all_distinct_values(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get(client, film_sim="Provia")

        assert "Provia" in response.context["film_simulations"]
        assert "Velvia" in response.context["film_simulations"]

    def test_active_film_simulation_context_matches_param(self, client):
        FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get(client, film_sim="Velvia")

        assert response.context["active_film_simulation"] == "Velvia"

    def test_graph_elements_json_is_valid_json(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get(client, film_sim="Provia")

        elements = json.loads(response.context["graph_elements_json"])
        assert isinstance(elements, list)


# ---------------------------------------------------------------------------
# Graph page — edges
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesGraphViewEdges:
    def test_no_edges_for_single_recipe(self, client):
        FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0, white_balance_blue=0)

        response = _get(client, film_sim="Provia")

        assert _edges(response) == []

    def test_edge_present_between_close_recipes_in_same_film_sim(self, client):
        r1 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        r2 = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong", white_balance_red=0, white_balance_blue=0)

        response = _get(client, film_sim="Provia")

        edges = _edges(response)
        assert len(edges) == 1
        assert {edges[0]["data"]["source"], edges[0]["data"]["target"]} == {str(r1.pk), str(r2.pk)}

    def test_edge_data_includes_distance(self, client):
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong", white_balance_red=0, white_balance_blue=0)

        response = _get(client, film_sim="Provia")

        assert _edges(response)[0]["data"]["distance"] == 1


# ---------------------------------------------------------------------------
# Film sim filter — JSON endpoint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesGraphJsonFilter:
    def test_json_response_when_accept_header_is_application_json(self, client):
        response = _get_json(client, film_sim="Provia")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_json_response_contains_elements_key(self, client):
        response = _get_json(client, film_sim="Provia")

        data = json.loads(response.content)
        assert "elements" in data

    def test_json_response_returns_only_nodes_for_requested_film_sim(self, client):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get_json(client, film_sim="Provia")

        node_ids = {n["data"]["id"] for n in _json_nodes(response)}
        assert str(provia.pk) in node_ids
        assert str(velvia.pk) not in node_ids

    def test_json_response_switches_film_sim(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")
        velvia = FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get_json(client, film_sim="Velvia")

        node_ids = {n["data"]["id"] for n in _json_nodes(response)}
        assert str(velvia.pk) in node_ids

    def test_json_response_empty_when_no_recipes_for_film_sim(self, client):
        response = _get_json(client, film_sim="Provia")

        assert _json_nodes(response) == []
        assert _json_edges(response) == []

    def test_json_response_includes_edges(self, client):
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong", white_balance_red=0, white_balance_blue=0)

        response = _get_json(client, film_sim="Provia")

        assert len(_json_edges(response)) == 1

    def test_json_defaults_to_provia_without_film_sim_param(self, client):
        provia = FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Velvia")

        response = client.get("/recipes/graph/", HTTP_ACCEPT="application/json")

        node_ids = {n["data"]["id"] for n in _json_nodes(response)}
        assert str(provia.pk) in node_ids
