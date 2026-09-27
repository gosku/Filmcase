"""Integration tests for the database-side similarity queries."""

from decimal import Decimal

import pytest

from src.data import models
from src.domain.recipes import similarity
from tests.factories import FujifilmRecipeFactory


def _recipe(**overrides: object) -> models.FujifilmRecipe:
    """Create a saved recipe with the white-balance shift pinned (the factory
    otherwise sequences ``white_balance_red``, which would perturb distances)."""
    defaults: dict[str, object] = {"white_balance_red": 0, "white_balance_blue": 0}
    defaults.update(overrides)
    return FujifilmRecipeFactory(**defaults)


@pytest.mark.django_db
class TestAnnotateSimilarity:
    def test_matches_the_pure_reference_for_every_candidate(self) -> None:
        reference = _recipe(
            film_simulation="Classic Chrome", dynamic_range="DR400",
            color_chrome_effect="Strong", color_chrome_fx_blue="Weak",
            white_balance="5200K", white_balance_red=2, white_balance_blue=-4,
            highlight=Decimal("0.0"), shadow=Decimal("-2.0"), color=Decimal("2.0"),
            sharpness=Decimal("0.0"), high_iso_nr=Decimal("-4.0"), clarity=Decimal("0.0"),
        )
        candidates = [
            # A near-identical colour recipe.
            _recipe(
                film_simulation="Classic Chrome", dynamic_range="DR200",
                color_chrome_effect="Strong", color_chrome_fx_blue="Weak",
                white_balance="5200K", white_balance_red=2, white_balance_blue=-4,
                highlight=Decimal("0.0"), shadow=Decimal("-2.0"), color=Decimal("2.0"),
                sharpness=Decimal("-1.0"), high_iso_nr=Decimal("-2.0"), clarity=Decimal("0.0"),
            ),
            # A different colour simulation with its own tone.
            _recipe(
                film_simulation="Velvia", dynamic_range="DR100", white_balance="Daylight",
                white_balance_red=0, white_balance_blue=0, highlight=Decimal("1.0"),
                shadow=Decimal("2.0"), color=Decimal("4.0"), sharpness=Decimal("2.0"),
            ),
            # A black-and-white recipe (exercises the colour/B&W maxing).
            _recipe(
                film_simulation="Acros Yellow", dynamic_range="DR200", white_balance="Daylight",
                white_balance_red=9, white_balance_blue=-9, highlight=Decimal("0.0"),
                shadow=Decimal("3.0"), sharpness=Decimal("1.0"), high_iso_nr=Decimal("-2.0"),
                monochromatic_color_warm_cool=Decimal("0.0"), monochromatic_color_magenta_green=Decimal("0.0"),
            ),
        ]

        annotated = {
            row.pk: row.similarity
            for row in similarity.annotate_similarity(models.FujifilmRecipe.objects.all(), reference=reference)
        }
        for candidate in candidates:
            expected = similarity.compute_similarity(a=reference, b=candidate)
            assert annotated[candidate.pk] == pytest.approx(expected, abs=1e-9)

    def test_a_recipe_is_perfectly_similar_to_itself(self) -> None:
        reference = _recipe(film_simulation="Velvia", color=Decimal("2.0"))
        annotated = similarity.annotate_similarity(
            models.FujifilmRecipe.objects.filter(pk=reference.pk),
            reference=reference,
        ).get()
        assert annotated.similarity == pytest.approx(1.0)


@pytest.mark.django_db
class TestMostSimilarRecipes:
    def test_orders_by_descending_similarity_and_excludes_the_reference(self) -> None:
        reference = _recipe(
            film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("0.0"),
        )
        near = _recipe(
            film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-1.0"),
        )
        far = _recipe(film_simulation="Acros STD", monochromatic_color_warm_cool=Decimal("0.0"))

        results = list(similarity.most_similar_recipes(recipe_id=reference.pk))

        assert reference.pk not in [r.pk for r in results]
        assert [r.pk for r in results] == [near.pk, far.pk]
        assert results[0].similarity > results[1].similarity

    def test_limit_caps_the_number_of_results(self) -> None:
        reference = _recipe(film_simulation="Provia")
        # Distinct white-balance shifts keep the recipes off the unique constraint.
        for shift in range(1, 6):
            _recipe(film_simulation="Provia", white_balance_red=shift)

        results = list(similarity.most_similar_recipes(recipe_id=reference.pk, limit=2))

        assert len(results) == 2


@pytest.mark.django_db
class TestSimilarityBetween:
    def test_matches_the_pure_reference(self) -> None:
        a = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("0.0"))
        b = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"), sharpness=Decimal("-2.0"))

        result = similarity.similarity_between(recipe_id_a=a.pk, recipe_id_b=b.pk)

        assert result == pytest.approx(similarity.compute_similarity(a=a, b=b), abs=1e-9)

    def test_a_recipe_is_perfectly_similar_to_itself(self) -> None:
        recipe = _recipe(film_simulation="Velvia", color=Decimal("1.0"))
        assert similarity.similarity_between(recipe_id_a=recipe.pk, recipe_id_b=recipe.pk) == pytest.approx(1.0)

    def test_is_symmetric(self) -> None:
        a = _recipe(film_simulation="Classic Chrome", color=Decimal("2.0"))
        b = _recipe(film_simulation="Acros Yellow", monochromatic_color_warm_cool=Decimal("3.0"))

        forward = similarity.similarity_between(recipe_id_a=a.pk, recipe_id_b=b.pk)
        backward = similarity.similarity_between(recipe_id_a=b.pk, recipe_id_b=a.pk)

        assert forward == pytest.approx(backward, abs=1e-9)
