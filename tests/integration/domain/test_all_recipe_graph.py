import pytest

from src.domain.recipes.graph import (
    AllRecipeEdge,
    AllRecipeGraphData,
    AllRecipeNode,
    FilmSimTreeData,
    FilmSimTreeNode,
    build_all_recipe_graph,
    build_film_sim_tree,
)
from tests.factories import FujifilmRecipeFactory, ImageFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _recipe(film_simulation="Provia", **kwargs):
    """Create a recipe with all sequence-driven fields pinned to fixed values
    so hamming distances are determined solely by the fields under test."""
    defaults = {
        "film_simulation": film_simulation,
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


def _node_ids(graph):
    return {n.id for n in graph.nodes}


def _edge_pairs(graph):
    return {(e.source, e.target) for e in graph.edges}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildAllRecipeGraphNodes:
    def test_all_recipes_appear_as_nodes(self):
        r1 = _recipe()
        r2 = _recipe(film_simulation="Velvia")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert _node_ids(graph) == {r1.pk, r2.pk}

    def test_named_recipe_uses_name_as_label(self):
        r = _recipe()
        r.name = "Summer Velvia"
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        node = next(n for n in graph.nodes if n.id == r.pk)
        assert node.label == "Summer Velvia"

    def test_unnamed_recipe_uses_id_prefix_as_label(self):
        r = _recipe()
        assert r.name == ""
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        node = next(n for n in graph.nodes if n.id == r.pk)
        assert node.label == f"#{r.pk}"

    def test_node_carries_film_simulation(self):
        r = _recipe(film_simulation="Classic Chrome")
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        node = next(n for n in graph.nodes if n.id == r.pk)
        assert node.film_simulation == "Classic Chrome"

    def test_node_image_count_comes_from_provided_dict(self):
        r = _recipe()
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={r.pk: 42})
        node = next(n for n in graph.nodes if n.id == r.pk)
        assert node.image_count == 42

    def test_node_image_count_defaults_to_zero_when_absent(self):
        r = _recipe()
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        node = next(n for n in graph.nodes if n.id == r.pk)
        assert node.image_count == 0

    def test_returns_frozen_dataclasses(self):
        r = _recipe()
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        assert isinstance(graph, AllRecipeGraphData)
        assert isinstance(graph.nodes[0], AllRecipeNode)

    def test_empty_recipe_list_produces_empty_graph(self):
        graph = build_all_recipe_graph(all_recipes=[], image_counts={})
        assert graph.nodes == ()
        assert graph.edges == ()


# ---------------------------------------------------------------------------
# Edges — film simulation grouping
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildAllRecipeGraphFilmSimGrouping:
    def test_no_edge_between_different_film_simulations(self):
        # distance 1 between these two, but different film sims — no edge expected
        provia = _recipe(film_simulation="Provia", grain_roughness="Off")
        velvia = _recipe(film_simulation="Velvia", grain_roughness="Off")
        graph = build_all_recipe_graph(all_recipes=[provia, velvia], image_counts={})
        assert graph.edges == ()

    def test_edge_connects_recipes_in_same_film_sim(self):
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong")  # distance 1
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert len(graph.edges) == 1
        edge = graph.edges[0]
        assert {edge.source, edge.target} == {r1.pk, r2.pk}

    def test_two_film_sim_groups_produce_independent_edges(self):
        p1 = _recipe(film_simulation="Provia", grain_roughness="Off")
        p2 = _recipe(film_simulation="Provia", grain_roughness="Strong")
        v1 = _recipe(film_simulation="Velvia", grain_roughness="Off")
        v2 = _recipe(film_simulation="Velvia", grain_roughness="Strong")
        graph = build_all_recipe_graph(all_recipes=[p1, p2, v1, v2], image_counts={})
        pairs = _edge_pairs(graph)
        # Intra-group edges present
        assert {p1.pk, p2.pk} == {graph.edges[0].source, graph.edges[0].target} or \
               any({e.source, e.target} == {p1.pk, p2.pk} for e in graph.edges)
        assert any({e.source, e.target} == {v1.pk, v2.pk} for e in graph.edges)
        # No cross-group edges
        for e in graph.edges:
            node_pks = {e.source, e.target}
            assert not (node_pks & {p1.pk, p2.pk} and node_pks & {v1.pk, v2.pk})

    def test_solo_recipe_per_film_sim_has_no_edges(self):
        r = _recipe(film_simulation="ACROS")
        graph = build_all_recipe_graph(all_recipes=[r], image_counts={})
        assert graph.edges == ()


# ---------------------------------------------------------------------------
# Edges — distance values and max-distance cutoff
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildAllRecipeGraphEdgeDistances:
    def test_edge_distance_reflects_hamming_distance(self):
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert len(graph.edges) == 1
        assert graph.edges[0].distance == 1

    def test_edge_carries_correct_distance_for_two_field_difference(self):
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert len(graph.edges) == 1
        assert graph.edges[0].distance == 2

    def test_edge_returns_frozen_dataclass(self):
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert isinstance(graph.edges[0], AllRecipeEdge)

    def test_pair_beyond_max_distance_produces_no_edge(self):
        # Create two recipes that differ in 10 fields — beyond max distance of 9.
        # Fields used: grain_roughness, grain_size, color_chrome_effect,
        # color_chrome_fx_blue, dynamic_range, d_range_priority, white_balance,
        # white_balance_red, white_balance_blue, highlight (10 total).
        r1 = _recipe(
            film_simulation="Provia",
            grain_roughness="Off",
            grain_size="Off",
            color_chrome_effect="Off",
            color_chrome_fx_blue="Off",
            dynamic_range="DR100",
            d_range_priority="Off",
            white_balance="Auto",
            white_balance_red=0,
            white_balance_blue=0,
            highlight=None,
        )
        r2 = _recipe(
            film_simulation="Provia",
            grain_roughness="Strong",
            grain_size="Large",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Strong",
            dynamic_range="DR200",
            d_range_priority="Auto",
            white_balance="Daylight",
            white_balance_red=3,
            white_balance_blue=-3,
            highlight=1,
        )
        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=r1, b=r2) == 10
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert graph.edges == ()


# ---------------------------------------------------------------------------
# Edges — blocking constraint
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildAllRecipeGraphBlockingConstraint:
    def test_distance_1_edges_are_never_blocked(self):
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert any(e.distance == 1 for e in graph.edges)

    def test_distance_2_edges_are_never_blocked(self):
        # Even if r1 and r2 share only d-2 in common (no d-1 or d-0 neighbours),
        # distance-2 edges are always allowed.
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large")
        graph = build_all_recipe_graph(all_recipes=[r1, r2], image_counts={})
        assert any(e.distance == 2 for e in graph.edges)

    def test_distance_3_edge_blocked_when_node_has_d1_and_d2_neighbours(self):
        # r1-r2: distance 1, r1-r3: distance 2, r1-r4: distance 3.
        # r1 has d-1 and d-2 neighbours → r1 is blocked from d-3 edges.
        # r4 has only a d-3 connection to r1 and nothing closer → r4 not blocked.
        # But because r1 IS blocked, the (r1, r4) edge should be suppressed.
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")  # d=1 from r1
        r3 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large", color_chrome_effect="Off")  # d=2 from r1
        r4 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")  # d=3 from r1

        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=r1, b=r2) == 1
        assert hamming_distance(a=r1, b=r3) == 2
        assert hamming_distance(a=r1, b=r4) == 3

        graph = build_all_recipe_graph(all_recipes=[r1, r2, r3, r4], image_counts={})

        # r1 must not appear in any d=3 edge
        d3_edges = [e for e in graph.edges if e.distance == 3]
        assert not any(e.source == r1.pk or e.target == r1.pk for e in d3_edges)

    def test_distance_3_edge_allowed_when_node_has_d2_but_not_d1(self):
        # r1-r2: distance 2, r1-r3: distance 3.  r1 has d-2 but NOT d-1 → not blocked for d-3.
        # r3 has only a d-3 connection → not blocked either.
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large", color_chrome_effect="Off")  # d=2 from r1
        r3 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")  # d=3 from r1

        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=r1, b=r2) == 2
        assert hamming_distance(a=r1, b=r3) == 3
        # Confirm r1 has no d=1 neighbour in this set
        assert hamming_distance(a=r2, b=r3) == 1  # r2-r3 are d=1 apart but that's a separate pair

        graph = build_all_recipe_graph(all_recipes=[r1, r2, r3], image_counts={})

        d3_edges = [e for e in graph.edges if e.distance == 3]
        assert any(
            {e.source, e.target} == {r1.pk, r3.pk}
            for e in d3_edges
        )

    def test_distance_3_edge_allowed_when_node_has_d1_but_not_d2(self):
        # r1-r2: distance 1, r1-r3: distance 3, no d-2 neighbour for r1.
        # Constraint requires BOTH d-1 AND d-2 to block; only d-1 present → not blocked.
        r1 = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")  # d=1
        r3 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")  # d=3 from r1

        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=r1, b=r2) == 1
        assert hamming_distance(a=r1, b=r3) == 3
        # Confirm no d=2 neighbour for r1 in this set
        assert hamming_distance(a=r2, b=r3) == 2  # r2-r3 differ in 2 fields

        graph = build_all_recipe_graph(all_recipes=[r1, r2, r3], image_counts={})

        d3_edges = [e for e in graph.edges if e.distance == 3]
        assert any(
            {e.source, e.target} == {r1.pk, r3.pk}
            for e in d3_edges
        )


# ---------------------------------------------------------------------------
# build_film_sim_tree
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildFilmSimTreeNodes:
    def test_all_recipes_appear_as_nodes(self):
        r1 = _recipe(film_simulation="Provia")
        r2 = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_film_sim_tree(root=r1, all_recipes=[r1, r2], image_counts={})
        assert {n.id for n in graph.nodes} == {r1.pk, r2.pk}

    def test_root_has_distance_zero(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.distance == 0

    def test_direct_child_has_hop_depth_one(self):
        root = _recipe(film_simulation="Provia", grain_roughness="Off")
        other = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_film_sim_tree(root=root, all_recipes=[root, other], image_counts={})
        node = next(n for n in graph.nodes if n.id == other.pk)
        assert node.distance == 1

    def test_chained_node_has_hop_depth_two(self):
        # root → n2 → n3: n3 is 1 step from n2, which is 1 step from root.
        # Prim's attaches n2 first (closest to root), then n3 to n2.
        root = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off")
        n2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Off")
        n3 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large")
        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=root, b=n2) == 1
        assert hamming_distance(a=n2, b=n3) == 1
        assert hamming_distance(a=root, b=n3) == 2
        graph = build_film_sim_tree(root=root, all_recipes=[root, n2, n3], image_counts={})
        node = next(n for n in graph.nodes if n.id == n3.pk)
        assert node.distance == 2

    def test_includes_nodes_at_any_distance_with_no_cutoff(self):
        # Create a recipe far from root (distance > 9, which was the old max).
        root = _recipe(
            film_simulation="Provia",
            grain_roughness="Off", grain_size="Off",
            color_chrome_effect="Off", color_chrome_fx_blue="Off",
            dynamic_range="DR100", d_range_priority="Off",
            white_balance="Auto", white_balance_red=0, white_balance_blue=0,
            highlight=None,
        )
        far = _recipe(
            film_simulation="Provia",
            grain_roughness="Strong", grain_size="Large",
            color_chrome_effect="Strong", color_chrome_fx_blue="Strong",
            dynamic_range="DR200", d_range_priority="Auto",
            white_balance="Daylight", white_balance_red=3, white_balance_blue=-3,
            highlight=1,
        )
        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=root, b=far) == 10

        graph = build_film_sim_tree(root=root, all_recipes=[root, far], image_counts={})

        assert far.pk in {n.id for n in graph.nodes}

    def test_named_recipe_uses_name_as_label(self):
        root = _recipe(film_simulation="Provia")
        root.name = "My Provia"
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.label == "My Provia"

    def test_unnamed_recipe_uses_id_prefix_as_label(self):
        root = _recipe(film_simulation="Provia")
        assert root.name == ""
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.label == f"#{root.pk}"

    def test_node_image_count_comes_from_provided_dict(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={root.pk: 7})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.image_count == 7

    def test_node_image_count_defaults_to_zero(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.image_count == 0

    def test_returns_frozen_dataclasses(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        assert isinstance(graph, FilmSimTreeData)
        assert isinstance(graph.nodes[0], FilmSimTreeNode)

    def test_root_id_is_set_correctly(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        assert graph.root_id == root.pk


@pytest.mark.django_db
class TestBuildFilmSimTreeEdges:
    def test_solo_root_has_no_edges(self):
        root = _recipe(film_simulation="Provia")
        graph = build_film_sim_tree(root=root, all_recipes=[root], image_counts={})
        assert graph.edges == ()

    def test_direct_neighbour_connects_to_root(self):
        root = _recipe(film_simulation="Provia", grain_roughness="Off")
        child = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_film_sim_tree(root=root, all_recipes=[root, child], image_counts={})
        assert any(
            {e.source, e.target} == {root.pk, child.pk}
            for e in graph.edges
        )

    def test_chain_topology_connects_via_nearest_intermediate(self):
        root = _recipe(film_simulation="Provia", grain_roughness="Off", grain_size="Off")
        n2 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Off")
        n3 = _recipe(film_simulation="Provia", grain_roughness="Strong", grain_size="Large")

        from src.domain.recipes.graph import hamming_distance
        assert hamming_distance(a=root, b=n2) == 1
        assert hamming_distance(a=root, b=n3) == 2
        assert hamming_distance(a=n2, b=n3) == 1

        graph = build_film_sim_tree(root=root, all_recipes=[root, n2, n3], image_counts={})

        assert any(e.source == n2.pk and e.target == n3.pk for e in graph.edges)
        assert not any(e.source == root.pk and e.target == n3.pk for e in graph.edges)

    def test_edge_distance_reflects_hamming_between_connected_nodes(self):
        root = _recipe(film_simulation="Provia", grain_roughness="Off")
        child = _recipe(film_simulation="Provia", grain_roughness="Strong")
        graph = build_film_sim_tree(root=root, all_recipes=[root, child], image_counts={})
        edge = next(e for e in graph.edges if {e.source, e.target} == {root.pk, child.pk})
        assert edge.distance == 1
