import json

import pytest
from bs4 import BeautifulSoup

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

    def test_film_simulations_context_excludes_sims_with_only_one_recipe(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")
        FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong")
        FujifilmRecipeFactory(film_simulation="Velvia")

        response = _get(client, film_sim="Provia")

        assert "Provia" in response.context["film_simulations"]
        assert "Velvia" not in response.context["film_simulations"]

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


# ---------------------------------------------------------------------------
# Per-recipe graph — /recipes/graph/<recipe_id>/
# ---------------------------------------------------------------------------

def _recipe(film_simulation=_DEFAULT_SIM, **kwargs):
    defaults = {
        "film_simulation": film_simulation,
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


def _graph_body_stray_text(response):
    """
    Return any non-whitespace text sitting directly inside .graph-body.

    The canvas and the panel are flex siblings, so a bare text node between them
    becomes an anonymous flex item whose width collapses the canvas to zero and
    the graph silently stops rendering. A leaked template comment is one way to
    introduce one.
    """
    soup = BeautifulSoup(response.content, "html.parser")
    body = soup.find(class_="graph-body")
    assert body is not None, "graph-body container is missing"
    return "".join(
        child for child in body.find_all(string=True, recursive=False)
    ).strip()


@pytest.mark.django_db
class TestGraphNamedOnlyFilter:
    def test_named_param_drops_unnamed_recipes_from_the_network(self, client):
        named = _recipe(name="Named", grain_roughness="Off")
        unnamed = _recipe(name="", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM, "named": "1"})

        node_ids = {n["data"]["id"] for n in _nodes(response)}
        assert str(named.pk) in node_ids
        assert str(unnamed.pk) not in node_ids

    def test_without_the_param_every_recipe_is_shown(self, client):
        _recipe(name="Named", grain_roughness="Off")
        unnamed = _recipe(name="", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        assert str(unnamed.pk) in {n["data"]["id"] for n in _nodes(response)}
        assert response.context["named_only"] is False

    def test_named_param_is_reflected_in_the_context(self, client):
        _recipe(name="Named")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM, "named": "1"})

        assert response.context["named_only"] is True

    def test_named_param_applies_to_the_per_recipe_graph(self, client):
        root = _recipe(name="Root", grain_roughness="Off")
        unnamed = _recipe(name="", grain_roughness="Strong")

        response = client.get(f"/recipes/graph/{root.pk}/", {"named": "1"})

        elements = json.loads(response.context["graph_elements_json"])
        node_ids = {e["data"]["id"] for e in elements if "source" not in e["data"]}
        assert str(unnamed.pk) not in node_ids
        assert response.context["named_only"] is True

    def test_nodes_carry_the_is_named_flag(self, client):
        named = _recipe(name="Named", grain_roughness="Off")
        unnamed = _recipe(name="", grain_roughness="Strong")

        response = client.get("/recipes/graph/", {"film_sim": _DEFAULT_SIM})

        by_id = {n["data"]["id"]: n["data"] for n in _nodes(response)}
        assert by_id[str(named.pk)]["is_named"] is True
        assert by_id[str(unnamed.pk)]["is_named"] is False


@pytest.mark.django_db
class TestGraphPagesHaveNoStrayCanvasSiblings:
    def test_film_sim_graph_body_contains_no_bare_text(self, client):
        _recipe()

        response = client.get("/recipes/graph/?film_sim=Provia")

        assert _graph_body_stray_text(response) == ""

    def test_per_recipe_graph_body_contains_no_bare_text(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        assert _graph_body_stray_text(response) == ""

    @pytest.mark.parametrize("url_template", ["/recipes/graph/", "/recipes/graph/{pk}/"])
    def test_no_template_comment_leaks_into_the_page(self, client, url_template):
        recipe = _recipe()

        response = client.get(url_template.format(pk=recipe.pk))

        assert "{#" not in response.content.decode()


@pytest.mark.django_db
class TestRecipeGraphView:
    def test_renders_ok_for_an_existing_recipe(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        assert response.status_code == 200

    def test_returns_404_for_an_unknown_recipe(self, client):
        response = client.get("/recipes/graph/999999/")

        assert response.status_code == 404

    def test_root_id_is_the_requested_recipe(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        assert response.context["root_id"] == recipe.pk

    def test_graph_elements_json_is_valid_json(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        elements = json.loads(response.context["graph_elements_json"])
        assert isinstance(elements, list)

    def test_recipe_name_is_passed_to_the_template(self, client):
        recipe = _recipe()
        recipe.name = "My Provia"
        recipe.save()

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        assert response.context["recipe_name"] == "My Provia"

    def test_nearby_recipe_appears_as_a_node(self, client):
        root = _recipe(grain_roughness="Off")
        close = _recipe(grain_roughness="Strong")

        response = client.get(f"/recipes/graph/{root.pk}/")

        elements = json.loads(response.context["graph_elements_json"])
        node_ids = {e["data"]["id"] for e in elements if "source" not in e["data"]}
        assert str(close.pk) in node_ids

    def test_edges_carry_the_is_exact_flag(self, client):
        root = _recipe(grain_roughness="Off")
        _recipe(grain_roughness="Strong")

        response = client.get(f"/recipes/graph/{root.pk}/")

        elements = json.loads(response.context["graph_elements_json"])
        edges = [e["data"] for e in elements if "source" in e["data"]]
        assert len(edges) == 1
        assert edges[0]["is_exact"] is True


@pytest.mark.django_db
class TestRecipeGraphJson:
    def test_json_response_when_accept_header_is_application_json(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/", HTTP_ACCEPT="application/json")

        assert response.status_code == 200
        assert response["Content-Type"] == "application/json"

    def test_json_response_contains_root_and_elements(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/", HTTP_ACCEPT="application/json")

        data = json.loads(response.content)
        assert data["root_id"] == recipe.pk
        assert isinstance(data["elements"], list)

    def test_json_root_label_falls_back_to_id_prefix(self, client):
        recipe = _recipe()

        response = client.get(f"/recipes/graph/{recipe.pk}/", HTTP_ACCEPT="application/json")

        data = json.loads(response.content)
        assert data["root_label"] == f"#{recipe.pk}"

    def test_json_path_sums_match_node_distances(self, client):
        # The invariant the per-recipe graph previously broke, checked end to end.
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        _recipe(grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")
        _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Off")

        response = client.get(f"/recipes/graph/{root.pk}/", HTTP_ACCEPT="application/json")

        data = json.loads(response.content)
        node_distance = {
            e["data"]["id"]: e["data"]["distance"]
            for e in data["elements"] if "source" not in e["data"]
        }
        parent_of = {
            e["data"]["target"]: e["data"]["source"]
            for e in data["elements"] if "source" in e["data"]
        }
        edge_distance = {
            e["data"]["target"]: e["data"]["distance"]
            for e in data["elements"] if "source" in e["data"]
        }

        for node_id in node_distance:
            pk = node_id
            total = 0
            while pk in parent_of:
                total += edge_distance[pk]
                pk = parent_of[pk]
            assert total == node_distance[node_id]
