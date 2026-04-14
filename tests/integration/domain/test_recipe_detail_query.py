import pytest

from src.data.models import FujifilmRecipe
from src.domain.recipes.queries import RecipeData, RecipeDetailContext, get_recipe_detail, get_recipe_gallery_data
from src.domain.recipes.constants import MONOCHROMATIC_FILM_SIMULATIONS
from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGetRecipeDetail:
    def test_returns_recipe_detail_context(self):
        recipe = FujifilmRecipeFactory()

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert isinstance(result, RecipeDetailContext)

    def test_returns_recipe_data_for_existing_recipe(self):
        recipe = FujifilmRecipeFactory(name="Velvet Dream", film_simulation="Velvia")

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert isinstance(result.recipe, RecipeData)
        assert result.recipe.id == recipe.pk
        assert result.recipe.name == "Velvet Dream"
        assert result.recipe.film_simulation == "Velvia"

    def test_raises_does_not_exist_for_missing_recipe(self):
        with pytest.raises(FujifilmRecipe.DoesNotExist):
            get_recipe_detail(recipe_id=99999)

    def test_image_count_is_zero_when_no_images(self):
        recipe = FujifilmRecipeFactory()

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.image_count == 0

    def test_image_count_reflects_associated_images(self):
        recipe = FujifilmRecipeFactory()
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.image_count == 3

    def test_image_count_excludes_images_from_other_recipes(self):
        recipe_a = FujifilmRecipeFactory()
        recipe_b = FujifilmRecipeFactory()
        ImageFactory(fujifilm_recipe=recipe_a)
        ImageFactory.create_batch(2, fujifilm_recipe=recipe_b)

        result = get_recipe_detail(recipe_id=recipe_a.pk)

        assert result.recipe.image_count == 1

    def test_cover_image_id_is_none_when_no_images(self):
        recipe = FujifilmRecipeFactory()

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.cover_image_id is None

    def test_cover_image_id_is_set_when_images_exist(self):
        recipe = FujifilmRecipeFactory()
        image = ImageFactory(fujifilm_recipe=recipe)

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.cover_image_id == image.pk

    def test_cover_image_id_uses_explicit_cover_when_set(self):
        recipe = FujifilmRecipeFactory()
        cover = ImageFactory(fujifilm_recipe=recipe, rating=0)
        _popular = ImageFactory(fujifilm_recipe=recipe, rating=5)
        recipe.set_cover_image(image_id=cover.pk)

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.cover_image_id == cover.pk

    def test_cover_image_id_falls_back_to_subquery_when_no_explicit_cover(self):
        recipe = FujifilmRecipeFactory()
        _low_rated = ImageFactory(fujifilm_recipe=recipe, rating=1)
        high_rated = ImageFactory(fujifilm_recipe=recipe, rating=5)

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.recipe.cover_image_id == high_rated.pk

    def test_is_monochromatic_is_true_for_monochromatic_film_simulation(self):
        mono_sim = next(iter(MONOCHROMATIC_FILM_SIMULATIONS))
        recipe = FujifilmRecipeFactory(film_simulation=mono_sim)

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.is_monochromatic is True

    def test_is_monochromatic_is_false_for_colour_film_simulation(self):
        recipe = FujifilmRecipeFactory(film_simulation="Provia")

        result = get_recipe_detail(recipe_id=recipe.pk)

        assert result.is_monochromatic is False

    def test_all_recipe_settings_are_returned(self):
        recipe = FujifilmRecipeFactory(
            dynamic_range="DR200",
            grain_roughness="Strong",
            grain_size="Large",
            color_chrome_effect="Strong",
            white_balance="Daylight",
        )

        result = get_recipe_detail(recipe_id=recipe.pk)
        r = result.recipe

        assert r.dynamic_range == "DR200"
        assert r.grain_roughness == "Strong"
        assert r.grain_size == "Large"
        assert r.color_chrome_effect == "Strong"
        assert r.white_balance == "Daylight"


@pytest.mark.django_db
class TestGetRecipeGalleryDataCoverImage:
    def _get_cover_id(self, recipe):
        result = get_recipe_gallery_data(
            active_filters={},
            page_number=1,
            page_size=50,
        )
        return next(r.cover_image_id for r in result.page_obj.items if r.id == recipe.pk)

    def test_cover_image_id_is_none_when_no_images(self):
        recipe = FujifilmRecipeFactory()
        assert self._get_cover_id(recipe) is None

    def test_cover_image_id_falls_back_to_subquery_when_no_explicit_cover(self):
        recipe = FujifilmRecipeFactory()
        _low_rated = ImageFactory(fujifilm_recipe=recipe, rating=1)
        high_rated = ImageFactory(fujifilm_recipe=recipe, rating=5)

        assert self._get_cover_id(recipe) == high_rated.pk

    def test_cover_image_id_uses_explicit_cover_when_set(self):
        recipe = FujifilmRecipeFactory()
        cover = ImageFactory(fujifilm_recipe=recipe, rating=0)
        _popular = ImageFactory(fujifilm_recipe=recipe, rating=5)
        recipe.set_cover_image(image_id=cover.pk)

        assert self._get_cover_id(recipe) == cover.pk
