from pathlib import Path

from django.conf import settings

from src.data import models
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates


def create_recipe_card(
    *,
    recipe_id: int,
    image_id: int | None,
    template: card_templates.CardTemplate,
) -> models.RecipeCard:
    """Create a recipe card for the given recipe and persist it.

    :raises FujifilmRecipe.DoesNotExist: If recipe_id does not exist.
    :raises Image.DoesNotExist: If image_id is given but does not exist.
    """
    recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    background_image = (
        models.Image.objects.get(pk=image_id) if image_id is not None else None
    )
    output_dir = Path(settings.RECIPE_CARDS_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    return card_operations.create_recipe_card(
        recipe=recipe,
        template=template,
        background_image=background_image,
        output_dir=output_dir,
    )
