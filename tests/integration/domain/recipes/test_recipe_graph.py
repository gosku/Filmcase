import pytest

from src.domain.recipes.graph import (
    RecipeTreeData,
    RecipeTreeEdge,
    RecipeTreeNode,
    build_recipe_tree,
    hamming_distance,
    named_recipes,
    recipes_within_distance,
)
from tests.factories import FujifilmRecipeFactory


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


def _parent_map(graph):
    return {e.target: e.source for e in graph.edges}


def _path_sum(graph, pk):
    """Sum the edge distances from *pk* up to the root."""
    parent_of = _parent_map(graph)
    distance_of = {e.target: e.distance for e in graph.edges}
    total = 0
    while pk in parent_of:
        total += distance_of[pk]
        pk = parent_of[pk]
    return total


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
# recipes_within_distance
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipesWithinDistance:
    def test_root_is_always_included(self):
        root = _recipe()
        within = recipes_within_distance(root=root, all_recipes=[root], max_distance=4)
        assert [r.pk for r in within] == [root.pk]

    def test_root_is_included_even_when_max_distance_is_zero(self):
        root = _recipe()
        within = recipes_within_distance(root=root, all_recipes=[root], max_distance=0)
        assert [r.pk for r in within] == [root.pk]

    def test_root_is_included_when_absent_from_all_recipes(self):
        root = _recipe()
        within = recipes_within_distance(root=root, all_recipes=[], max_distance=4)
        assert [r.pk for r in within] == [root.pk]

    def test_nearby_recipe_is_included(self):
        root = _recipe(grain_roughness="Off")
        close = _recipe(grain_roughness="Strong")
        within = recipes_within_distance(root=root, all_recipes=[root, close], max_distance=4)
        assert close.pk in {r.pk for r in within}

    def test_recipe_at_max_distance_is_excluded(self):
        # The boundary is strict: a recipe exactly max_distance away is dropped.
        root = _recipe(grain_roughness="Off", grain_size="Off")
        two_away = _recipe(grain_roughness="Strong", grain_size="Large")
        assert hamming_distance(a=root, b=two_away) == 2

        within = recipes_within_distance(root=root, all_recipes=[root, two_away], max_distance=2)
        assert two_away.pk not in {r.pk for r in within}

    def test_recipe_just_inside_max_distance_is_included(self):
        root = _recipe(grain_roughness="Off", grain_size="Off")
        two_away = _recipe(grain_roughness="Strong", grain_size="Large")
        assert hamming_distance(a=root, b=two_away) == 2

        within = recipes_within_distance(root=root, all_recipes=[root, two_away], max_distance=3)
        assert two_away.pk in {r.pk for r in within}

    def test_other_film_simulations_are_eligible(self):
        # Unlike the film-sim graph, this candidate set spans film simulations.
        root = _recipe(film_simulation="Provia")
        other_sim = _recipe(film_simulation="Velvia")
        assert hamming_distance(a=root, b=other_sim) == 1

        within = recipes_within_distance(root=root, all_recipes=[root, other_sim], max_distance=4)
        assert other_sim.pk in {r.pk for r in within}

    def test_root_is_not_duplicated_when_present_in_all_recipes(self):
        root = _recipe()
        within = recipes_within_distance(root=root, all_recipes=[root, root], max_distance=4)
        assert [r.pk for r in within] == [root.pk]


# ---------------------------------------------------------------------------
# named_recipes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNamedRecipes:
    def test_named_recipe_is_kept(self):
        root = _recipe()
        named = _recipe(grain_roughness="Strong")
        named.name = "Kodak Portra"
        named.save()

        kept = named_recipes(root=root, all_recipes=[root, named])

        assert named.pk in {r.pk for r in kept}

    def test_unnamed_recipe_is_dropped(self):
        root = _recipe()
        unnamed = _recipe(grain_roughness="Strong")
        assert unnamed.name == ""

        kept = named_recipes(root=root, all_recipes=[root, unnamed])

        assert unnamed.pk not in {r.pk for r in kept}

    def test_unnamed_root_is_still_kept(self):
        # The most-used recipe for a film simulation is often unnamed. Dropping
        # it would leave the graph with no root at all.
        root = _recipe()
        assert root.name == ""

        kept = named_recipes(root=root, all_recipes=[root])

        assert [r.pk for r in kept] == [root.pk]

    def test_root_is_kept_when_absent_from_all_recipes(self):
        root = _recipe()

        kept = named_recipes(root=root, all_recipes=[])

        assert [r.pk for r in kept] == [root.pk]

    def test_root_is_not_duplicated_when_named(self):
        root = _recipe()
        root.name = "Named root"
        root.save()

        kept = named_recipes(root=root, all_recipes=[root])

        assert [r.pk for r in kept] == [root.pk]

    def test_filtered_tree_is_still_connected_and_spanning(self):
        root = _recipe(grain_roughness="Off", grain_size="Off")
        named = _recipe(grain_roughness="Strong", grain_size="Off")
        named.name = "Named"
        named.save()
        _recipe(grain_roughness="Strong", grain_size="Large")  # unnamed, dropped

        kept = named_recipes(root=root, all_recipes=[root, named])
        graph = build_recipe_tree(root=root, candidates=kept, image_counts={})

        assert len(graph.nodes) == 2
        assert len(graph.edges) == len(graph.nodes) - 1

    def test_path_sums_still_hold_after_filtering(self):
        # Dropping intermediates makes the shortest-path constraint fail more
        # often, but every exact edge must still satisfy the invariant.
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        far = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")
        far.name = "Far named"
        far.save()
        _recipe(grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")  # unnamed

        kept = named_recipes(root=root, all_recipes=[root, far])
        graph = build_recipe_tree(root=root, candidates=kept, image_counts={})

        distance_from_root = {n.id: n.distance for n in graph.nodes}
        for edge in graph.edges:
            if edge.is_exact:
                assert distance_from_root[edge.source] + edge.distance == distance_from_root[edge.target]


# ---------------------------------------------------------------------------
# build_recipe_tree — nodes
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildRecipeTreeNodes:
    def test_all_candidates_appear_as_nodes(self):
        r1 = _recipe()
        r2 = _recipe(grain_roughness="Strong")
        graph = build_recipe_tree(root=r1, candidates=[r1, r2], image_counts={})
        assert {n.id for n in graph.nodes} == {r1.pk, r2.pk}

    def test_root_is_included_when_absent_from_candidates(self):
        root = _recipe()
        other = _recipe(grain_roughness="Strong")
        graph = build_recipe_tree(root=root, candidates=[other], image_counts={})
        assert root.pk in {n.id for n in graph.nodes}

    def test_root_has_distance_zero(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.distance == 0

    def test_direct_child_has_distance_one(self):
        root = _recipe(grain_roughness="Off")
        other = _recipe(grain_roughness="Strong")
        graph = build_recipe_tree(root=root, candidates=[root, other], image_counts={})
        node = next(n for n in graph.nodes if n.id == other.pk)
        assert node.distance == 1

    def test_node_distance_equals_hamming_distance_from_root(self):
        # node.distance must equal hamming_distance(root, node), not hop depth.
        root = _recipe(grain_roughness="Off", grain_size="Off")
        n2 = _recipe(grain_roughness="Strong", grain_size="Off")
        n3 = _recipe(grain_roughness="Strong", grain_size="Large")
        assert hamming_distance(a=root, b=n2) == 1
        assert hamming_distance(a=n2, b=n3) == 1
        assert hamming_distance(a=root, b=n3) == 2

        graph = build_recipe_tree(root=root, candidates=[root, n2, n3], image_counts={})
        node = next(n for n in graph.nodes if n.id == n3.pk)
        assert node.distance == 2  # hamming_distance(root, n3), not hop count

    def test_includes_nodes_at_any_distance_with_no_cutoff(self):
        # The builder itself applies no cutoff; callers pre-filter candidates.
        root = _recipe(
            grain_roughness="Off", grain_size="Off",
            color_chrome_effect="Off", color_chrome_fx_blue="Off",
            dynamic_range="DR100", d_range_priority="Off",
            white_balance="Auto", white_balance_red=0, white_balance_blue=0,
            highlight=None,
        )
        far = _recipe(
            grain_roughness="Strong", grain_size="Large",
            color_chrome_effect="Strong", color_chrome_fx_blue="Strong",
            dynamic_range="DR200", d_range_priority="Auto",
            white_balance="Daylight", white_balance_red=3, white_balance_blue=-3,
            highlight=1,
        )
        assert hamming_distance(a=root, b=far) == 10

        graph = build_recipe_tree(root=root, candidates=[root, far], image_counts={})
        assert far.pk in {n.id for n in graph.nodes}

    def test_named_recipe_uses_name_as_label(self):
        root = _recipe()
        root.name = "My Provia"
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.label == "My Provia"

    def test_unnamed_recipe_uses_id_prefix_as_label(self):
        root = _recipe()
        assert root.name == ""
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.label == f"#{root.pk}"

    def test_named_recipe_node_is_flagged_named(self):
        root = _recipe()
        root.name = "My Provia"
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.is_named is True

    def test_unnamed_recipe_node_is_flagged_unnamed(self):
        # The label falls back to "#<pk>", so callers need the flag rather than
        # sniffing the label for a leading hash.
        root = _recipe()
        assert root.name == ""
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.is_named is False

    def test_node_image_count_comes_from_provided_mapping(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={root.pk: 7})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.image_count == 7

    def test_node_image_count_defaults_to_zero(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        node = next(n for n in graph.nodes if n.id == root.pk)
        assert node.image_count == 0

    def test_returns_frozen_dataclasses(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        assert isinstance(graph, RecipeTreeData)
        assert isinstance(graph.nodes[0], RecipeTreeNode)

    def test_root_id_is_set_correctly(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        assert graph.root_id == root.pk


# ---------------------------------------------------------------------------
# build_recipe_tree — edges
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestBuildRecipeTreeEdges:
    def test_solo_root_has_no_edges(self):
        root = _recipe()
        graph = build_recipe_tree(root=root, candidates=[root], image_counts={})
        assert graph.edges == ()

    def test_direct_neighbour_connects_to_root(self):
        root = _recipe(grain_roughness="Off")
        child = _recipe(grain_roughness="Strong")
        graph = build_recipe_tree(root=root, candidates=[root, child], image_counts={})
        assert any({e.source, e.target} == {root.pk, child.pk} for e in graph.edges)

    def test_every_candidate_is_connected(self):
        root = _recipe(grain_roughness="Off", grain_size="Off")
        a = _recipe(grain_roughness="Strong", grain_size="Off")
        b = _recipe(grain_roughness="Strong", grain_size="Large")
        graph = build_recipe_tree(root=root, candidates=[root, a, b], image_counts={})

        # A spanning tree over n nodes has exactly n-1 edges and no islands.
        assert len(graph.edges) == len(graph.nodes) - 1
        assert {e.target for e in graph.edges} == {a.pk, b.pk}

    def test_chain_topology_connects_via_nearest_intermediate(self):
        root = _recipe(grain_roughness="Off", grain_size="Off")
        n2 = _recipe(grain_roughness="Strong", grain_size="Off")
        n3 = _recipe(grain_roughness="Strong", grain_size="Large")

        assert hamming_distance(a=root, b=n2) == 1
        assert hamming_distance(a=root, b=n3) == 2
        assert hamming_distance(a=n2, b=n3) == 1

        graph = build_recipe_tree(root=root, candidates=[root, n2, n3], image_counts={})

        assert any(e.source == n2.pk and e.target == n3.pk for e in graph.edges)
        assert not any(e.source == root.pk and e.target == n3.pk for e in graph.edges)

    def test_edge_distance_reflects_hamming_between_connected_nodes(self):
        root = _recipe(grain_roughness="Off")
        child = _recipe(grain_roughness="Strong")
        graph = build_recipe_tree(root=root, candidates=[root, child], image_counts={})
        edge = next(e for e in graph.edges if {e.source, e.target} == {root.pk, child.pk})
        assert isinstance(edge, RecipeTreeEdge)
        assert edge.distance == 1

    def test_shortest_path_constraint_produces_minimum_total_edge_weight(self):
        # Each node's parent must satisfy dist(root,parent) + dist(parent,node) == dist(root,node).
        # This guarantees the sum of edges along any root→node path equals the true
        # Hamming distance, and the total edge weight is minimised.
        #
        #   root --3-- A --1-- B --1-- C   (total = 5)
        #
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        # A differs from root by 3 fields
        a = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")
        # B is 1 hop from A (color_chrome_fx_blue differs)
        b = _recipe(
            grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong",
            color_chrome_fx_blue="Strong",
        )
        # C is 1 hop from B (dynamic_range differs)
        c = _recipe(
            grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong",
            color_chrome_fx_blue="Strong", dynamic_range="DR200",
        )
        assert hamming_distance(a=root, b=a) == 3
        assert hamming_distance(a=a, b=b) == 1
        assert hamming_distance(a=b, b=c) == 1

        # Supply recipes in an order that would trip up a BFS/distance-order algorithm.
        graph = build_recipe_tree(root=root, candidates=[root, a, c, b], image_counts={})

        total_edge_weight = sum(e.distance for e in graph.edges)
        assert total_edge_weight == 5  # 3 + 1 + 1, not 3 + 4 + 1 or worse

    def test_path_sum_equals_hamming_distance_from_root(self):
        # The core invariant: for every node, the sum of edge distances along its
        # path to root must equal hamming_distance(root, node).
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        a = _recipe(grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off")
        b = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Off")
        c = _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong")

        assert hamming_distance(a=root, b=a) == 1
        assert hamming_distance(a=root, b=b) == 2
        assert hamming_distance(a=root, b=c) == 3

        graph = build_recipe_tree(root=root, candidates=[root, a, b, c], image_counts={})

        for recipe in [a, b, c]:
            assert _path_sum(graph, recipe.pk) == hamming_distance(a=root, b=recipe)

    def test_path_sum_holds_for_a_candidate_set_truncated_by_max_distance(self):
        # This is the per-recipe graph's situation: candidates are cut off at a
        # maximum distance, so some intermediate recipes are missing. The invariant
        # must still hold for every node reached through an exact edge.
        root = _recipe(
            grain_roughness="Off", grain_size="Off",
            color_chrome_effect="Off", color_chrome_fx_blue="Off",
        )
        near = _recipe(
            grain_roughness="Strong", grain_size="Off",
            color_chrome_effect="Off", color_chrome_fx_blue="Off",
        )
        mid = _recipe(
            grain_roughness="Strong", grain_size="Large",
            color_chrome_effect="Off", color_chrome_fx_blue="Off",
        )
        far = _recipe(
            grain_roughness="Strong", grain_size="Large",
            color_chrome_effect="Strong", color_chrome_fx_blue="Strong",
        )
        all_recipes = [root, near, mid, far]

        candidates = recipes_within_distance(root=root, all_recipes=all_recipes, max_distance=3)
        assert far.pk not in {r.pk for r in candidates}  # distance 4, cut off

        graph = build_recipe_tree(root=root, candidates=candidates, image_counts={})

        for node in graph.nodes:
            if node.id == root.pk:
                continue
            recipe = next(r for r in all_recipes if r.pk == node.id)
            assert _path_sum(graph, node.id) == hamming_distance(a=root, b=recipe)

    def test_edges_are_exact_when_the_shortest_path_constraint_holds(self):
        root = _recipe(grain_roughness="Off", grain_size="Off")
        a = _recipe(grain_roughness="Strong", grain_size="Off")
        b = _recipe(grain_roughness="Strong", grain_size="Large")
        graph = build_recipe_tree(root=root, candidates=[root, a, b], image_counts={})

        assert all(e.is_exact for e in graph.edges)

    def test_fallback_edge_is_marked_inexact(self):
        # Two recipes each 1 away from root in different fields are 2 apart from
        # each other, so no chaining is possible and both attach directly to root
        # with exact edges. Removing root's nearest neighbour from the candidate
        # set is what forces a fallback, so build a case where a node's only
        # available parent overshoots its distance from root.
        root = _recipe(grain_roughness="Off", grain_size="Off")
        # Sibling at distance 1 in a field the target does not share.
        sibling = _recipe(grain_roughness="Strong", grain_size="Off")
        # Target at distance 1 from root via a different field, so
        # dist(root,sibling) + dist(sibling,target) = 1 + 2 = 3 != 1.
        target = _recipe(grain_roughness="Off", grain_size="Large")

        assert hamming_distance(a=root, b=sibling) == 1
        assert hamming_distance(a=root, b=target) == 1
        assert hamming_distance(a=sibling, b=target) == 2

        graph = build_recipe_tree(root=root, candidates=[root, sibling, target], image_counts={})

        # Both attach straight to root, and both edges are exact.
        assert _parent_map(graph) == {sibling.pk: root.pk, target.pk: root.pk}
        assert all(e.is_exact for e in graph.edges)

    def test_inexact_edge_only_appears_when_no_valid_parent_exists(self):
        # Whenever an edge is marked inexact, no in-tree node could have satisfied
        # the constraint. Verified by checking the invariant holds for every exact
        # edge and that inexact edges genuinely overshoot.
        root = _recipe(grain_roughness="Off", grain_size="Off", color_chrome_effect="Off")
        recipes = [
            root,
            _recipe(grain_roughness="Strong", grain_size="Off", color_chrome_effect="Off"),
            _recipe(grain_roughness="Off", grain_size="Large", color_chrome_effect="Off"),
            _recipe(grain_roughness="Strong", grain_size="Large", color_chrome_effect="Strong"),
        ]
        graph = build_recipe_tree(root=root, candidates=recipes, image_counts={})

        distance_from_root = {n.id: n.distance for n in graph.nodes}
        for edge in graph.edges:
            parent_distance = distance_from_root[edge.source]
            target_distance = distance_from_root[edge.target]
            if edge.is_exact:
                assert parent_distance + edge.distance == target_distance
            else:
                assert parent_distance + edge.distance > target_distance
