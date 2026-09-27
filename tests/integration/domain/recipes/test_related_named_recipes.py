"""Integration tests for get_related_named_recipes."""

from decimal import Decimal

import pytest

from src.data import models
from src.domain.recipes import queries, similarity
from tests.factories import (
    FujifilmRecipeFactory,
    ImageFactory,
    RecipeGroupFactory,
    RecipeGroupMemberFactory,
)


def _recipe(**overrides: object) -> models.FujifilmRecipe:
    """Create a saved recipe with the white-balance shift pinned so distances
    are driven only by the fields under test."""
    defaults: dict[str, object] = {"white_balance_red": 0, "white_balance_blue": 0}
    defaults.update(overrides)
    return FujifilmRecipeFactory(**defaults)


@pytest.mark.django_db
class TestGetRelatedNamedRecipes:
    def test_excludes_the_reference_and_unnamed_recipes(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"))
        named = _recipe(name="Named", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))
        _recipe(name="", film_simulation="Classic Chrome", color=Decimal("3.0"), white_balance_red=3)

        results = queries.get_related_named_recipes(recipe_id=reference.pk)

        ids = [r.id for r in results]
        assert reference.pk not in ids
        assert ids == [named.pk]

    def test_orders_by_descending_similarity(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("0.0"))
        near = _recipe(name="Near", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))
        other_colour = _recipe(name="Velvia", film_simulation="Velvia", color=Decimal("2.0"), white_balance_red=1)
        black_and_white = _recipe(name="Acros", film_simulation="Acros STD", monochromatic_color_warm_cool=Decimal("0.0"), white_balance_red=2)

        results = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert [r.id for r in results] == [near.pk, other_colour.pk, black_and_white.pk]
        assert results[0].similarity > results[1].similarity > results[2].similarity

    def test_limit_caps_the_results(self) -> None:
        reference = _recipe(film_simulation="Provia")
        for shift in range(1, 6):
            _recipe(name=f"Recipe {shift}", film_simulation="Provia", white_balance_red=shift)

        results = queries.get_related_named_recipes(recipe_id=reference.pk, limit=2)

        assert len(results) == 2

    def test_returns_fewer_when_few_named_recipes_exist(self) -> None:
        reference = _recipe(film_simulation="Provia")
        only_named = _recipe(name="Only one", film_simulation="Provia", white_balance_red=1)

        results = queries.get_related_named_recipes(recipe_id=reference.pk, limit=4)

        assert [r.id for r in results] == [only_named.pk]

    def test_excludes_recipes_in_the_same_version_line(self) -> None:
        reference = _recipe(name="Reference", film_simulation="Classic Chrome", color=Decimal("2.0"))
        sibling = _recipe(name="Sibling", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))
        outsider = _recipe(name="Outsider", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-2.0"))
        version_line = RecipeGroupFactory()
        RecipeGroupMemberFactory(group=version_line, recipe=reference, position=1)
        RecipeGroupMemberFactory(group=version_line, recipe=sibling, position=2)

        ids = [r.id for r in queries.get_related_named_recipes(recipe_id=reference.pk)]

        assert sibling.pk not in ids
        assert outsider.pk in ids

    def test_collapses_other_version_lines_to_their_most_similar_member(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("0.0"))
        # One other version line with three members of decreasing similarity.
        best = _recipe(name="Line best", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))
        mid = _recipe(name="Line mid", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-3.0"))
        worst = _recipe(name="Line worst", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-4.0"))
        line = RecipeGroupFactory()
        RecipeGroupMemberFactory(group=line, recipe=best, position=1)
        RecipeGroupMemberFactory(group=line, recipe=mid, position=2)
        RecipeGroupMemberFactory(group=line, recipe=worst, position=3)
        # A standalone recipe (no version line) is kept on its own.
        standalone = _recipe(name="Standalone", film_simulation="Velvia", color=Decimal("2.0"), white_balance_red=4)

        ids = [r.id for r in queries.get_related_named_recipes(recipe_id=reference.pk)]

        assert best.pk in ids
        assert mid.pk not in ids
        assert worst.pk not in ids
        assert standalone.pk in ids

    def test_returns_empty_when_no_named_recipes_exist(self) -> None:
        reference = _recipe(film_simulation="Provia")
        _recipe(name="", film_simulation="Provia", white_balance_red=1)

        results = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert results == ()

    def test_similarity_matches_the_metric(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"))
        candidate = _recipe(name="Candidate", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-2.0"))

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.similarity == pytest.approx(similarity.compute_similarity(a=reference, b=candidate), abs=1e-9)

    def test_carries_the_cover_image(self) -> None:
        reference = _recipe(film_simulation="Provia")
        candidate = _recipe(name="With cover", film_simulation="Provia", white_balance_red=1)
        ImageFactory(fujifilm_recipe=candidate, rating=2)
        top = ImageFactory(fujifilm_recipe=candidate, rating=5)

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.cover_image_id == top.pk

    def test_carries_top_image_ids_for_the_mosaic(self) -> None:
        reference = _recipe(film_simulation="Provia")
        candidate = _recipe(name="With shots", film_simulation="Provia", white_balance_red=1)
        low = ImageFactory(fujifilm_recipe=candidate, rating=1)
        mid = ImageFactory(fujifilm_recipe=candidate, rating=3)
        high = ImageFactory(fujifilm_recipe=candidate, rating=5)
        ImageFactory(fujifilm_recipe=candidate, rating=0)  # 4th, dropped (mosaic holds 3)

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.image_ids == (high.pk, mid.pk, low.pk)

    def test_image_ids_empty_without_images(self) -> None:
        reference = _recipe(film_simulation="Provia")
        _recipe(name="No shots", film_simulation="Provia", white_balance_red=1)

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.image_ids == ()

    def test_sets_closeness_label_from_similarity(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"))
        near = _recipe(name="Near", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))
        black_and_white = _recipe(name="Acros", film_simulation="Acros STD", monochromatic_color_warm_cool=Decimal("0.0"), white_balance_red=2)

        labels = {r.id: r.closeness_label for r in queries.get_related_named_recipes(recipe_id=reference.pk)}

        assert labels[near.pk] == "Very close"
        assert labels[black_and_white.pk] == "Loosely related"

    def test_cover_image_is_none_without_images(self) -> None:
        reference = _recipe(film_simulation="Provia")
        _recipe(name="No cover", film_simulation="Provia", white_balance_red=1)

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.cover_image_id is None

    def test_film_sim_logo_is_populated(self) -> None:
        reference = _recipe(film_simulation="Provia")
        _recipe(name="Velvia", film_simulation="Velvia", white_balance_red=1)

        [result] = queries.get_related_named_recipes(recipe_id=reference.pk)

        assert result.film_sim_logo_filename == "velvia.png"


@pytest.mark.django_db
class TestGetRecipeDetailIncludesRelated:
    def test_detail_context_carries_related_recipes(self) -> None:
        reference = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"))
        neighbour = _recipe(name="Neighbour", film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"))

        detail = queries.get_recipe_detail(recipe_id=reference.pk)

        assert [r.id for r in detail.related_recipes] == [neighbour.pk]
