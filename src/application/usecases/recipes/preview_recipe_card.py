from pathlib import Path

from src.data import models
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import templates as card_templates

_TMP_DIR = Path("/tmp")


def preview_recipe_card(
    *,
    recipe_id: int,
    image_id: int | None,
    template: card_templates.CardTemplate,
) -> Path:
    """Generate a recipe card preview in /tmp/ and return its path.

    The output path is deterministic from the arguments, so repeated calls with
    the same options overwrite the previous file rather than accumulating.

    :raises FujifilmRecipe.DoesNotExist: If recipe_id does not exist.
    :raises Image.DoesNotExist: If image_id is given but does not exist.
    """
    recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    background_image = (
        models.Image.objects.get(pk=image_id) if image_id is not None else None
    )
    image_suffix = str(image_id) if image_id is not None else "none"
    output_path = _TMP_DIR / f"recipe_preview_{recipe_id}_{template.template_name}_{image_suffix}.jpg"
    return card_operations.preview_recipe_card_image(
        recipe=recipe,
        template=template,
        background_image=background_image,
        output_path=output_path,
    )
