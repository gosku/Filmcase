import pytest

from src.domain.recipes.queries import FieldValue, PathDeltaResult, get_path_deltas
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestGetPathDeltasEmptyAndMissing:
    def test_empty_ids_returns_empty_result(self):
        result = get_path_deltas(path_ids=[])

        assert result == PathDeltaResult(root_diffs=(), path_nodes=(), missing_ids=())

    def test_missing_ids_recorded_in_result(self):
        result = get_path_deltas(path_ids=[99999])

        assert 99999 in result.missing_ids
        assert result.path_nodes == ()


@pytest.mark.django_db
class TestGetPathDeltasSingleNode:
    def test_single_node_root_has_all_fields(self):
        recipe = FujifilmRecipeFactory(
            film_simulation="Provia",
            highlight=None,
            shadow=None,
            color=None,
        )

        result = get_path_deltas(path_ids=[recipe.pk])

        assert len(result.path_nodes) == 1
        root_node = result.path_nodes[0]
        field_names = {f.field for f in root_node.changed_fields}
        assert "Film Simulation" in field_names

    def test_single_node_root_diffs_is_empty(self):
        recipe = FujifilmRecipeFactory()

        result = get_path_deltas(path_ids=[recipe.pk])

        assert result.root_diffs == ()

    def test_single_node_label_uses_recipe_name(self):
        recipe = FujifilmRecipeFactory(name="Street Provia")

        result = get_path_deltas(path_ids=[recipe.pk])

        assert result.path_nodes[0].label == "Street Provia"

    def test_single_node_label_uses_pk_when_unnamed(self):
        recipe = FujifilmRecipeFactory(name="")

        result = get_path_deltas(path_ids=[recipe.pk])

        assert result.path_nodes[0].label == f"#{recipe.pk}"


@pytest.mark.django_db
class TestGetPathDeltasTwoNodes:
    def test_root_node_contains_all_non_null_fields(self):
        root = FujifilmRecipeFactory(film_simulation="Provia", highlight=None, shadow=None)
        clicked = FujifilmRecipeFactory(film_simulation="Provia", grain_roughness="Strong", highlight=None, shadow=None)

        result = get_path_deltas(path_ids=[root.pk, clicked.pk])

        root_node = result.path_nodes[0]
        root_fields = {f.field for f in root_node.changed_fields}
        assert "Film Simulation" in root_fields
        assert "Grain" in root_fields

    def test_clicked_node_shows_only_changed_fields(self):
        root = FujifilmRecipeFactory(grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        clicked = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Strong",
            white_balance_red=0,
            white_balance_blue=0,
        )

        result = get_path_deltas(path_ids=[root.pk, clicked.pk])

        clicked_node = result.path_nodes[1]
        changed_field_names = {f.field for f in clicked_node.changed_fields}
        assert "Grain" in changed_field_names
        # Film Simulation is the same — must not appear
        assert "Film Simulation" not in changed_field_names

    def test_root_diffs_matches_direct_comparison(self):
        root = FujifilmRecipeFactory(grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        clicked = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Strong",
            white_balance_red=0,
            white_balance_blue=0,
        )

        result = get_path_deltas(path_ids=[root.pk, clicked.pk])

        diff_field_names = {f.field for f in result.root_diffs}
        assert "Grain" in diff_field_names
        assert "Film Simulation" not in diff_field_names

    def test_root_diffs_uses_clicked_values(self):
        root = FujifilmRecipeFactory(grain_roughness="Off", white_balance_red=0, white_balance_blue=0)
        clicked = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Strong",
            white_balance_red=0,
            white_balance_blue=0,
        )

        result = get_path_deltas(path_ids=[root.pk, clicked.pk])

        grain_diff = next(f for f in result.root_diffs if f.field == "Grain")
        assert grain_diff.value == "Strong"

    def test_no_differences_gives_empty_root_diffs(self):
        # Pass the same recipe as both root and clicked — a recipe cannot differ from itself.
        recipe = FujifilmRecipeFactory()

        result = get_path_deltas(path_ids=[recipe.pk, recipe.pk])

        assert result.root_diffs == ()


@pytest.mark.django_db
class TestGetPathDeltasThreeNodes:
    def test_intermediate_node_delta_is_vs_previous_not_root(self):
        # Use white_balance_red to uniquify each recipe
        root = FujifilmRecipeFactory(
            grain_roughness="Off",
            white_balance_red=10,
            white_balance_blue=0,
            highlight=None,
            shadow=None,
            color=None,
        )
        mid = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Weak",
            white_balance_red=11,
            white_balance_blue=0,
            highlight=None,
            shadow=None,
            color=None,
        )
        clicked = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Strong",
            white_balance_red=12,
            white_balance_blue=0,
            highlight=None,
            shadow=None,
            color=None,
        )

        result = get_path_deltas(path_ids=[root.pk, mid.pk, clicked.pk])

        mid_node = result.path_nodes[1]
        clicked_node = result.path_nodes[2]

        mid_fields = {f.field for f in mid_node.changed_fields}
        clicked_fields = {f.field for f in clicked_node.changed_fields}

        # Mid changed grain vs root
        assert "Grain" in mid_fields
        # Clicked changed grain vs mid (root and mid both differ from clicked)
        assert "Grain" in clicked_fields

    def test_root_diffs_is_direct_root_vs_clicked_not_stepwise(self):
        # Root={grain:Off, wb:10}, Mid={grain:Strong, wb:11}, Clicked={grain:Off, wb:10}
        # root_diffs for grain must be empty since root and clicked share grain=Off.
        # Use same pk for root and clicked to avoid unique constraint.
        root = FujifilmRecipeFactory(
            grain_roughness="Off",
            white_balance_red=10,
            white_balance_blue=0,
        )
        mid = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            grain_roughness="Strong",
            white_balance_red=11,
            white_balance_blue=0,
        )

        # Clicked has same fields as root — pass root.pk again at the end of path
        result = get_path_deltas(path_ids=[root.pk, mid.pk, root.pk])

        diff_fields = {f.field for f in result.root_diffs}
        # Root and clicked (root again) are identical — no diffs
        assert diff_fields == set()

    def test_path_preserves_ordering(self):
        r1 = FujifilmRecipeFactory(white_balance_red=1, white_balance_blue=0)
        r2 = FujifilmRecipeFactory(white_balance_red=2, white_balance_blue=0)
        r3 = FujifilmRecipeFactory(white_balance_red=3, white_balance_blue=0)

        result = get_path_deltas(path_ids=[r1.pk, r2.pk, r3.pk])

        assert result.path_nodes[0].recipe_id == r1.pk
        assert result.path_nodes[1].recipe_id == r2.pk
        assert result.path_nodes[2].recipe_id == r3.pk

    def test_missing_ids_in_middle_are_skipped(self):
        r1 = FujifilmRecipeFactory(white_balance_red=1, white_balance_blue=0)
        r3 = FujifilmRecipeFactory(white_balance_red=3, white_balance_blue=0)

        result = get_path_deltas(path_ids=[r1.pk, 99999, r3.pk])

        assert 99999 in result.missing_ids
        present_ids = [n.recipe_id for n in result.path_nodes]
        assert 99999 not in present_ids


@pytest.mark.django_db
class TestGetPathDeltasDecimalFields:
    def test_decimal_field_formatted_with_sign(self):
        root = FujifilmRecipeFactory(highlight=None, white_balance_red=0, white_balance_blue=0)
        clicked = FujifilmRecipeFactory(
            film_simulation=root.film_simulation,
            white_balance_red=0,
            white_balance_blue=0,
            highlight=2,
        )

        result = get_path_deltas(path_ids=[root.pk, clicked.pk])

        highlight_diff = next((f for f in result.root_diffs if f.field == "Highlight"), None)
        assert highlight_diff is not None
        assert highlight_diff.value == "+2"

    def test_null_decimal_field_omitted_from_root(self):
        recipe = FujifilmRecipeFactory(highlight=None, white_balance_red=0, white_balance_blue=0)

        result = get_path_deltas(path_ids=[recipe.pk])

        root_field_names = {f.field for f in result.path_nodes[0].changed_fields}
        assert "Highlight" not in root_field_names
