import pytest

from src.domain.recipes.graph import (
    RecipeEdge,
    RecipeGraphData,
    RecipeNode,
    build_recipe_graph,
    hamming_distance,
)
from tests.factories import FujifilmRecipeFactory


# ---------------------------------------------------------------------------
# hamming_distance
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHammingDistance:
    def test_identical_recipes_have_distance_zero(self):
        recipe = FujifilmRecipeFactory()
        assert hamming_distance(a=recipe, b=recipe) == 0

    def test_single_field_difference(self):
        base = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0)
        other = FujifilmRecipeFactory(film_simulation="Velvia", white_balance_red=0)
        assert hamming_distance(a=base, b=other) == 1

    def test_two_field_differences(self):
        base = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0)
        other = FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Strong", white_balance_red=0)
        assert hamming_distance(a=base, b=other) == 2

    def test_distance_is_symmetric(self):
        a = FujifilmRecipeFactory(film_simulation="Provia")
        b = FujifilmRecipeFactory(film_simulation="Velvia")
        assert hamming_distance(a=a, b=b) == hamming_distance(a=b, b=a)

    def test_white_balance_fine_tune_counts_per_channel(self):
        # white_balance_red and white_balance_blue are separate fields
        base = FujifilmRecipeFactory(white_balance_red=0, white_balance_blue=0)
        other = FujifilmRecipeFactory(white_balance_red=2, white_balance_blue=-3)
        assert hamming_distance(a=base, b=other) == 2


# ---------------------------------------------------------------------------
# build_recipe_graph — nodes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildRecipeGraphNodes:
    def test_root_node_always_included(self):
        root = FujifilmRecipeFactory()
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        node_ids = {n.id for n in graph.nodes}
        assert root.pk in node_ids

    def test_root_node_has_distance_zero(self):
        root = FujifilmRecipeFactory()
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        root_node = next(n for n in graph.nodes if n.id == root.pk)
        assert root_node.distance == 0

    def test_nearby_recipe_included(self):
        root = FujifilmRecipeFactory(film_simulation="Provia")
        close = FujifilmRecipeFactory(film_simulation="Velvia")  # distance 1
        graph = build_recipe_graph(root=root, all_recipes=[root, close], max_distance=4)
        assert close.pk in {n.id for n in graph.nodes}

    def test_node_distance_reflects_hamming_distance_from_root(self):
        root = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0)
        close = FujifilmRecipeFactory(film_simulation="Velvia", white_balance_red=0)  # distance 1
        graph = build_recipe_graph(root=root, all_recipes=[root, close], max_distance=4)
        node = next(n for n in graph.nodes if n.id == close.pk)
        assert node.distance == 1

    def test_recipe_beyond_max_distance_excluded(self):
        root = FujifilmRecipeFactory(
            film_simulation="Provia",
            grain_roughness="Off",
            color_chrome_effect="Off",
            color_chrome_fx_blue="Off",
            white_balance="Auto",
        )
        # Make a recipe that differs in all five fields above → distance 5
        far = FujifilmRecipeFactory(
            film_simulation="Velvia",
            grain_roughness="Strong",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Strong",
            white_balance="Daylight",
        )
        assert hamming_distance(a=root, b=far) >= 4
        graph = build_recipe_graph(root=root, all_recipes=[root, far], max_distance=4)
        assert far.pk not in {n.id for n in graph.nodes}

    def test_unnamed_recipe_label_uses_id_prefix(self):
        root = FujifilmRecipeFactory(name="")
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        root_node = next(n for n in graph.nodes if n.id == root.pk)
        assert root_node.label == f"#{root.pk}"

    def test_named_recipe_label_uses_name(self):
        root = FujifilmRecipeFactory(name="My Recipe")
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        root_node = next(n for n in graph.nodes if n.id == root.pk)
        assert root_node.label == "My Recipe"

    def test_returns_frozen_dataclass(self):
        root = FujifilmRecipeFactory()
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        assert isinstance(graph, RecipeGraphData)
        assert isinstance(graph.nodes[0], RecipeNode)


# ---------------------------------------------------------------------------
# build_recipe_graph — edges
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildRecipeGraphEdges:
    def test_solo_root_has_no_edges(self):
        root = FujifilmRecipeFactory()
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        assert graph.edges == ()

    def test_direct_neighbour_connects_to_root(self):
        root = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0)
        close = FujifilmRecipeFactory(film_simulation="Velvia", white_balance_red=0)
        graph = build_recipe_graph(root=root, all_recipes=[root, close], max_distance=4)
        assert any(e.source == root.pk and e.target == close.pk for e in graph.edges)

    def test_chain_topology_avoids_direct_root_connection(self):
        """N3 is 1 step from N2 and 2 steps from root → should connect via N2."""
        root = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Off", white_balance_red=0)
        n2 = FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Off", white_balance_red=0)
        n3 = FujifilmRecipeFactory(film_simulation="Velvia", grain_roughness="Strong", white_balance_red=0)

        assert hamming_distance(a=root, b=n2) == 1
        assert hamming_distance(a=root, b=n3) == 2
        assert hamming_distance(a=n2, b=n3) == 1

        graph = build_recipe_graph(root=root, all_recipes=[root, n2, n3], max_distance=4)

        # n3 must connect through n2, not directly to root
        assert any(e.source == n2.pk and e.target == n3.pk for e in graph.edges)
        assert not any(e.source == root.pk and e.target == n3.pk for e in graph.edges)

    def test_island_prevention_connects_to_root_when_no_intermediate(self):
        """A node at distance 3 with nothing at distance 2 or 1 must still connect."""
        root = FujifilmRecipeFactory(
            film_simulation="Provia",
            grain_roughness="Off",
            color_chrome_effect="Off",
            white_balance_red=0,
        )
        distant = FujifilmRecipeFactory(
            film_simulation="Velvia",
            grain_roughness="Strong",
            color_chrome_effect="Strong",
            white_balance_red=0,
        )
        assert hamming_distance(a=root, b=distant) == 3

        # Only these two — no intermediate nodes
        graph = build_recipe_graph(root=root, all_recipes=[root, distant], max_distance=4)
        edge_sources = {e.source for e in graph.edges}
        assert root.pk in edge_sources  # root must be the source since no intermediates

    def test_edge_distance_reflects_hamming_between_connected_nodes(self):
        root = FujifilmRecipeFactory(film_simulation="Provia", white_balance_red=0)
        close = FujifilmRecipeFactory(film_simulation="Velvia", white_balance_red=0)
        graph = build_recipe_graph(root=root, all_recipes=[root, close], max_distance=4)
        edge = next(e for e in graph.edges if e.target == close.pk)
        assert isinstance(edge, RecipeEdge)
        assert edge.distance == 1

    def test_root_id_is_set_correctly(self):
        root = FujifilmRecipeFactory()
        graph = build_recipe_graph(root=root, all_recipes=[root], max_distance=4)
        assert graph.root_id == root.pk
