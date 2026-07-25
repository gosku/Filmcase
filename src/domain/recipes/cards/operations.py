from __future__ import annotations

import tempfile
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path

import attrs
from PIL import Image as PILImage

from django.db import transaction

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import rendering
from src.domain.recipes.cards.designs import base as card_designs


def _save_card(
    *,
    canvas: PILImage.Image,
    filepath: Path,
    json_str: str,
    embed_exif: bool,
) -> None:
    canvas.save(str(filepath), format="JPEG", quality=90)
    if embed_exif:
        rendering.embed_recipe_exif(filepath=filepath, json_str=json_str)


def preview_recipe_card_image(
    *,
    recipe: models.FujifilmRecipe,
    design: card_designs.CardDesign,
    background_image: models.Image | None,
    output_path: Path,
) -> Path:
    """
    Compose a recipe card image and save it to output_path. Return output_path.

    Intended for previews: the caller controls the exact output path (e.g. a
    deterministic /tmp/ path) so successive previews for the same options
    overwrite the previous file rather than accumulating.
    """
    rendered = design.render(recipe=recipe, background_image=background_image)
    _save_card(
        canvas=rendered.canvas,
        filepath=output_path,
        json_str=rendered.json_str,
        embed_exif=rendered.embed_exif,
    )
    return output_path


def create_recipe_card_image(
    *,
    recipe: models.FujifilmRecipe,
    design: card_designs.CardDesign,
    background_image: models.Image | None,
    output_dir: Path,
) -> Path:
    """
    Compose a recipe card image and save it to output_dir. Return the file path.

    The *design* controls the entire layout. When background_image is None the
    design falls back to a generated gradient and the recipe JSON is embedded in
    the EXIF UserComment so the card can be re-imported without the QR.
    """
    rendered = design.render(recipe=recipe, background_image=background_image)
    filepath = output_dir / f"recipe_{recipe.pk}_{uuid.uuid4().hex[:8]}.jpg"
    _save_card(
        canvas=rendered.canvas,
        filepath=filepath,
        json_str=rendered.json_str,
        embed_exif=rendered.embed_exif,
    )
    return filepath


def create_recipe_card(
    *,
    recipe: models.FujifilmRecipe,
    design: card_designs.CardDesign,
    background_image: models.Image | None,
    output_dir: Path,
) -> models.RecipeCard:
    """
    Create a recipe card image, persist a RecipeCard record, and publish an event.

    Calls create_recipe_card_image internally, then saves a RecipeCard to the DB
    and publishes a recipe.card.created event.
    """
    filepath = create_recipe_card_image(
        recipe=recipe,
        design=design,
        background_image=background_image,
        output_dir=output_dir,
    )
    card = models.RecipeCard.create(
        filepath=str(filepath),
        template=design.template_name,
        recipe_id=recipe.pk,
        image_id=background_image.pk if background_image is not None else None,
    )
    events.publish_event(
        event_type=events.RECIPE_CARD_CREATED,
        recipe_id=recipe.pk,
        card_id=card.pk,
        template=design.template_name,
    )
    return card


@attrs.frozen
class RecipeCardFileMissingError(Exception):
    """
    Raised when a RecipeCard's JPEG file is missing from the filesystem.

    A RecipeCard record always implies its file exists, so a missing file
    indicates a corrupted state rather than an expected, handleable condition.
    """

    card_id: int
    filepath: str


def create_recipe_cards_zip(*, cards: Iterable[models.RecipeCard]) -> Path:
    """
    Bundle the JPEG files of *cards* into a zip archive in the temp directory.

    The archive is written to a uniquely named path under the system temp
    directory and is *not* cleaned up automatically: it must outlive this call
    so a download link can be served afterwards. Returns the archive path.

    :raises RecipeCardFileMissingError: If a card's file is not on disk.
    """
    # Validate every file exists before writing anything so we never leave a
    # partial archive on disk.
    cards = tuple(cards)
    for card in cards:
        if not Path(card.filepath).exists():
            raise RecipeCardFileMissingError(card_id=card.pk, filepath=card.filepath)

    zip_path = Path(tempfile.gettempdir()) / f"recipe_cards_{uuid.uuid4().hex[:8]}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for card in cards:
            source = Path(card.filepath)
            archive.write(source, arcname=source.name)
    card_count = len(cards)

    events.publish_event(
        event_type=events.RECIPE_CARDS_ZIP_CREATED,
        card_count=card_count,
        zip_path=str(zip_path),
    )
    return zip_path


@attrs.frozen
class RecipeCardNotFoundError(Exception):
    """
    Raised when no RecipeCard with the given ID exists.
    """

    card_id: int


def remove_recipe_card(*, card_id: int, remove_file: bool) -> None:
    """
    Delete the RecipeCard record and optionally remove its JPEG file from the filesystem.

    Uses atomic(durable=True) so this block is never nested inside an outer
    transaction. This guarantees the DB deletion commits before the file is
    removed — no outer rollback can undo the DB change after the file is gone.

    :raises RecipeCardNotFoundError: If no RecipeCard with *card_id* exists.
    """
    try:
        card = models.RecipeCard.objects.get(pk=card_id)
    except models.RecipeCard.DoesNotExist:
        raise RecipeCardNotFoundError(card_id=card_id)

    recipe_id = card.recipe_id
    filepath = card.filepath

    with transaction.atomic(durable=True):
        card.delete()
        if remove_file:
            path = Path(filepath)
            if path.exists():
                path.unlink()

    events.publish_event(
        event_type=events.RECIPE_CARD_REMOVED,
        card_id=card_id,
        recipe_id=recipe_id,
        filepath=filepath,
        remove_file=remove_file,
    )
