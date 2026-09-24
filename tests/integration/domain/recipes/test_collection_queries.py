import pytest

from src.data import models
from src.domain.recipes.queries import (
    CollectionDetailData,
    CollectionNotFound,
    get_collection_detail,
    get_collection_filter_options,
    get_collection_summaries,
    get_recipe_editor_options,
    get_recipes_for_collection_editor,
)
from tests.factories import (
    FujifilmRecipeFactory,
    ImageFactory,
    RecipeCollectionFactory,
    RecipeCollectionMemberFactory,
    RecipeGroupFactory,
    RecipeGroupMemberFactory,
)


@pytest.mark.django_db
class TestGetCollectionSummaries:
    def test_returns_a_card_per_collection(self):
        RecipeCollectionMemberFactory(group=RecipeCollectionFactory(name="A"))
        RecipeCollectionMemberFactory(group=RecipeCollectionFactory(name="B"))

        summaries = get_collection_summaries()

        assert [s.name for s in summaries] == ["A", "B"]

    def test_orders_by_name_case_insensitively(self):
        RecipeCollectionFactory(name="beta")
        RecipeCollectionFactory(name="Alpha")

        summaries = get_collection_summaries()

        assert [s.name for s in summaries] == ["Alpha", "beta"]

    def test_counts_recipes(self):
        group = RecipeCollectionFactory(name="Set")
        RecipeCollectionMemberFactory(group=group, position=0)
        RecipeCollectionMemberFactory(group=group, position=1)

        (summary,) = get_collection_summaries()

        assert summary.recipe_count == 2

    def test_excludes_version_line_and_family_groups(self):
        RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE)
        RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_FAMILY, name="Fam")

        assert get_collection_summaries() == []

    def test_filters_by_collection_name(self):
        RecipeCollectionFactory(name="Street Mono")
        RecipeCollectionFactory(name="Golden Hour")

        summaries = get_collection_summaries(name_search="mono")

        assert [s.name for s in summaries] == ["Street Mono"]

    def test_filters_by_recipe_name(self):
        wanted = RecipeCollectionFactory(name="Has Match")
        RecipeCollectionMemberFactory(
            group=wanted, recipe=FujifilmRecipeFactory(name="Kodak Tri-X")
        )
        other = RecipeCollectionFactory(name="No Match")
        RecipeCollectionMemberFactory(
            group=other, recipe=FujifilmRecipeFactory(name="Velvia Punch")
        )

        summaries = get_collection_summaries(recipe_name_search="tri-x")

        assert [s.name for s in summaries] == ["Has Match"]

    def test_filters_by_film_simulation(self):
        acros_col = RecipeCollectionFactory(name="Mono")
        RecipeCollectionMemberFactory(
            group=acros_col, recipe=FujifilmRecipeFactory(film_simulation="Acros STD")
        )
        provia_col = RecipeCollectionFactory(name="Color")
        RecipeCollectionMemberFactory(
            group=provia_col, recipe=FujifilmRecipeFactory(film_simulation="Provia")
        )

        summaries = get_collection_summaries(film_simulations=["Acros STD"])

        assert [s.name for s in summaries] == ["Mono"]

    def test_film_sims_carry_logo_and_are_ordered_by_frequency(self):
        group = RecipeCollectionFactory(name="Set")
        RecipeCollectionMemberFactory(
            group=group, position=0, recipe=FujifilmRecipeFactory(film_simulation="Provia")
        )
        RecipeCollectionMemberFactory(
            group=group, position=1, recipe=FujifilmRecipeFactory(film_simulation="Provia")
        )
        RecipeCollectionMemberFactory(
            group=group, position=2, recipe=FujifilmRecipeFactory(film_simulation="Acros STD")
        )

        (summary,) = get_collection_summaries()

        assert [fs.film_simulation for fs in summary.film_sims] == ["Provia", "Acros STD"]
        assert summary.film_sims[0].logo_filename == "provia.png"

    def test_mosaic_holds_best_rated_images_capped_at_four(self):
        group = RecipeCollectionFactory(name="Set")
        images = []
        for position, rating in enumerate([1, 5, 3, 2, 4]):
            recipe = FujifilmRecipeFactory()
            RecipeCollectionMemberFactory(group=group, recipe=recipe, position=position)
            images.append(ImageFactory(fujifilm_recipe=recipe, rating=rating))

        (summary,) = get_collection_summaries()

        # Top image per recipe, ordered by rating desc, first four.
        expected = [img.id for img in sorted(images, key=lambda i: i.rating, reverse=True)][:4]
        assert list(summary.mosaic_image_ids) == expected

    def test_mosaic_is_empty_when_no_recipe_has_an_image(self):
        group = RecipeCollectionFactory(name="Set")
        RecipeCollectionMemberFactory(group=group)

        (summary,) = get_collection_summaries()

        assert summary.mosaic_image_ids == ()


@pytest.mark.django_db
class TestGetCollectionFilterOptions:
    def test_counts_distinct_collections_per_film_simulation(self):
        col_a = RecipeCollectionFactory()
        col_b = RecipeCollectionFactory()
        RecipeCollectionMemberFactory(
            group=col_a, recipe=FujifilmRecipeFactory(film_simulation="Provia")
        )
        RecipeCollectionMemberFactory(
            group=col_b, recipe=FujifilmRecipeFactory(film_simulation="Provia")
        )
        RecipeCollectionMemberFactory(
            group=col_b, recipe=FujifilmRecipeFactory(film_simulation="Acros STD")
        )

        options = get_collection_filter_options()

        by_value = {f.value: f for f in options.film_simulations}
        assert by_value["Provia"].count == 2
        assert by_value["Acros STD"].count == 1

    def test_keeps_a_selected_value_with_no_matches_as_unavailable(self):
        options = get_collection_filter_options(selected_film_simulations=["Velvia"])

        (facet,) = options.film_simulations
        assert facet.value == "Velvia"
        assert facet.available is False
        assert facet.selected is True


@pytest.mark.django_db
class TestGetCollectionDetail:
    def test_raises_when_collection_missing(self):
        with pytest.raises(CollectionNotFound) as exc_info:
            get_collection_detail(collection_id=999)

        assert exc_info.value.collection_id == 999

    def test_raises_for_a_version_line_group_id(self):
        group = RecipeGroupFactory(group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE)

        with pytest.raises(CollectionNotFound):
            get_collection_detail(collection_id=group.pk)

    def test_returns_members_in_position_order(self):
        group = RecipeCollectionFactory(name="Ordered")
        first = FujifilmRecipeFactory(name="First")
        second = FujifilmRecipeFactory(name="Second")
        RecipeCollectionMemberFactory(group=group, recipe=second, position=1)
        RecipeCollectionMemberFactory(group=group, recipe=first, position=0)

        detail = get_collection_detail(collection_id=group.pk)

        assert isinstance(detail, CollectionDetailData)
        assert [m.name for m in detail.members] == ["First", "Second"]

    def test_member_carries_logo_and_image_count(self):
        group = RecipeCollectionFactory(name="Set")
        recipe = FujifilmRecipeFactory(film_simulation="Provia")
        RecipeCollectionMemberFactory(group=group, recipe=recipe, position=0)
        ImageFactory(fujifilm_recipe=recipe)
        ImageFactory(fujifilm_recipe=recipe)

        detail = get_collection_detail(collection_id=group.pk)

        (member,) = detail.members
        assert member.film_sim_logo_filename == "provia.png"
        assert member.image_count == 2


@pytest.mark.django_db
class TestGetRecipesForCollectionEditor:
    def test_returns_recipes_matching_the_name_search(self):
        FujifilmRecipeFactory(name="Kodak Tri-X")
        FujifilmRecipeFactory(name="Velvia Punch")

        options = get_recipes_for_collection_editor(name_search="tri-x")

        assert [o.name for o in options] == ["Kodak Tri-X"]

    def test_flags_recipes_already_in_the_collection(self):
        group = RecipeCollectionFactory()
        member_recipe = FujifilmRecipeFactory(name="Inside")
        RecipeCollectionMemberFactory(group=group, recipe=member_recipe)
        FujifilmRecipeFactory(name="Outside")

        options = get_recipes_for_collection_editor(in_collection_id=group.pk)

        flags = {o.name: o.in_collection for o in options}
        assert flags["Inside"] is True
        assert flags["Outside"] is False

    def test_orders_named_then_most_used(self):
        popular = FujifilmRecipeFactory(name="Popular")
        ImageFactory(fujifilm_recipe=popular)
        ImageFactory(fujifilm_recipe=popular)
        FujifilmRecipeFactory(name="Quiet")

        options = get_recipes_for_collection_editor()

        assert [o.name for o in options][:2] == ["Popular", "Quiet"]


@pytest.mark.django_db
class TestGetRecipeEditorOptions:
    def test_returns_options_in_the_given_id_order(self):
        first = FujifilmRecipeFactory(name="First")
        second = FujifilmRecipeFactory(name="Second")

        options = get_recipe_editor_options(recipe_ids=[second.pk, first.pk])

        assert [o.recipe_id for o in options] == [second.pk, first.pk]
        assert all(o.in_collection for o in options)

    def test_skips_unknown_and_repeated_ids(self):
        recipe = FujifilmRecipeFactory()

        options = get_recipe_editor_options(recipe_ids=[recipe.pk, recipe.pk, 999999])

        assert [o.recipe_id for o in options] == [recipe.pk]
