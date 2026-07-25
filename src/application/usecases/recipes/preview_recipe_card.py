from pathlib import Path

from src.data import models
from src.domain.images.thumbnails import operations as thumbnail_operations
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards.designs import base as card_designs

_TMP_DIR = Path("/tmp")

# Previews render from the cached gallery-sized thumbnail rather than the
# full-resolution original. The blurred background and small hero don't need
# full resolution, and this reuses the thumbnail the gallery already generated,
# avoiding a fresh decode/resize of the multi-megapixel source on every preview.
_PREVIEW_SOURCE_WIDTH = 600


def preview_recipe_card(
    *,
    recipe_id: int,
    image_id: int | None,
    design: card_designs.CardDesign,
) -> Path:
    """
    Generate a recipe card preview in /tmp/ and return its path.

    The output path is deterministic from the arguments, so repeated calls with
    the same options overwrite the previous file rather than accumulating.

    :raises FujifilmRecipe.DoesNotExist: If recipe_id does not exist.
    :raises Image.DoesNotExist: If image_id is given but does not exist.
    """
    recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    background_photo_path: str | None = None
    if image_id is not None:
        image = models.Image.objects.get(pk=image_id)
        thumbnail_path = thumbnail_operations.generate_thumbnail(
            original_path=Path(image.filepath), width=_PREVIEW_SOURCE_WIDTH,
        )
        background_photo_path = str(thumbnail_path)
    image_suffix = str(image_id) if image_id is not None else "none"
    output_path = _TMP_DIR / f"recipe_preview_{recipe_id}_{design.template_name}_{image_suffix}.jpg"
    return card_operations.preview_recipe_card_image(
        recipe=recipe,
        design=design,
        background_photo_path=background_photo_path,
        output_path=output_path,
    )
