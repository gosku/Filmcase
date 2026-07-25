from __future__ import annotations

import tempfile
import uuid
import zipfile
from collections.abc import Iterable
from pathlib import Path

import attrs
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFilter

from django.db import transaction

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import rendering
from src.domain.recipes.cards import templates as card_templates

_QR_MARGIN = 20
_PANEL_ALPHA = 140  # 0-255 opacity of the text-readability overlay panel
_TEXT_PADDING = 40
_LINE_HEIGHT = 44
_FONT_SIZE = 28
_TITLE_FONT_SIZE = 34
_TITLE_LINE_HEIGHT = 56
_LABEL_COLOR = (220, 220, 220)
_VALUE_COLOR = (255, 255, 255)
_LOGO_PATH = Path(__file__).resolve().parents[3] / "interfaces" / "static" / "images" / "filmcase_stacked_full.png"
_LOGO_WIDTH = 320
_LOGO_PADDING = 20


def _compose_card(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    info_side: card_templates.InfoSide,
) -> rendering.RenderedCard:
    """
    Build the card PIL image.

    *info_side* chooses which half holds the info text + logo; the QR code
    goes on the opposite bottom corner.
    """
    target_w, target_h = template.output_size
    if background_image is None:
        canvas = rendering.build_gradient(target_w, target_h)
    else:
        with PILImage.open(background_image.filepath) as img:
            canvas = rendering.cover_fill(img.convert("RGB"), target_w, target_h)
        if template.background_effect == "blur":
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius=rendering.BLUR_RADIUS))

    panel_w = target_w // 2
    panel_x = 0 if info_side == "left" else target_w - panel_w
    overlay = PILImage.new("RGBA", (panel_w, target_h), (0, 0, 0, _PANEL_ALPHA))
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.paste(overlay, (panel_x, 0), overlay)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    label_font = rendering.load_font(_FONT_SIZE)
    value_font = rendering.load_font(_FONT_SIZE)
    lines = card_queries.get_recipe_cover_lines(recipe=recipe, label_style=template.label_style)
    x = panel_x + _TEXT_PADDING
    y = _TEXT_PADDING
    if recipe.name:
        title_font = rendering.load_font(_TITLE_FONT_SIZE)
        draw.text((x, y), recipe.name, font=title_font, fill=_VALUE_COLOR)
        y += _TITLE_LINE_HEIGHT
    for line in lines:
        if y + _LINE_HEIGHT > target_h - _TEXT_PADDING:
            break
        draw.text((x, y), f"{line.label}:", font=label_font, fill=_LABEL_COLOR)
        label_w = int(draw.textlength(f"{line.label}:", font=label_font))
        draw.text((x + label_w + 8, y), line.value, font=value_font, fill=_VALUE_COLOR)
        y += _LINE_HEIGHT

    json_str = card_queries.get_recipe_as_json(recipe=recipe)
    qr_img = rendering.make_qr(json_str)
    qr_x = _QR_MARGIN if info_side == "right" else target_w - rendering.QR_SIZE - _QR_MARGIN
    qr_pos = (qr_x, target_h - rendering.QR_SIZE - _QR_MARGIN)
    canvas.paste(qr_img, qr_pos)

    if _LOGO_PATH.exists():
        with PILImage.open(_LOGO_PATH) as logo_src:
            logo_rgba = logo_src.convert("RGBA")
            bbox = logo_rgba.getbbox()
            if bbox:
                logo_rgba = logo_rgba.crop(bbox)
            content_h = int(_LOGO_WIDTH * logo_rgba.height / logo_rgba.width)
            logo = logo_rgba.resize((_LOGO_WIDTH, content_h), PILImage.Resampling.LANCZOS)
        logo_x = panel_x + _TEXT_PADDING
        logo_y = target_h - content_h - _TEXT_PADDING
        white_bg = PILImage.new("RGBA", (_LOGO_WIDTH + _LOGO_PADDING * 2, content_h + _LOGO_PADDING * 2), (255, 255, 255, 255))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(white_bg, (logo_x - _LOGO_PADDING, logo_y - _LOGO_PADDING))
        canvas_rgba.paste(logo, (logo_x, logo_y), logo)
        canvas = canvas_rgba.convert("RGB")

    return rendering.RenderedCard(
        canvas=canvas,
        json_str=json_str,
        embed_exif=background_image is None,
    )


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
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_path: Path,
    info_side: card_templates.InfoSide = card_templates.DEFAULT_INFO_SIDE,
) -> Path:
    """
    Compose a recipe card image and save it to output_path. Return output_path.

    Intended for previews: the caller controls the exact output path (e.g. a
    deterministic /tmp/ path) so successive previews for the same options
    overwrite the previous file rather than accumulating.
    """
    rendered = _compose_card(
        recipe=recipe,
        template=template,
        background_image=background_image,
        info_side=info_side,
    )
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
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_dir: Path,
    info_side: card_templates.InfoSide = card_templates.DEFAULT_INFO_SIDE,
) -> Path:
    """
    Compose a recipe card image and save it to output_dir. Return the file path.

    If background_image is given, resizes/crops it to template.output_size and
    applies Gaussian blur when template.background_effect == "blur".
    If background_image is None, generates a soft gradient background and embeds
    the recipe JSON into the EXIF UserComment so the card can be re-imported.
    """
    rendered = _compose_card(
        recipe=recipe,
        template=template,
        background_image=background_image,
        info_side=info_side,
    )
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
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_dir: Path,
    info_side: card_templates.InfoSide = card_templates.DEFAULT_INFO_SIDE,
) -> models.RecipeCard:
    """
    Create a recipe card image, persist a RecipeCard record, and publish an event.

    Calls create_recipe_card_image internally, then saves a RecipeCard to the DB
    and publishes a recipe.card.created event.
    """
    filepath = create_recipe_card_image(
        recipe=recipe,
        template=template,
        background_image=background_image,
        output_dir=output_dir,
        info_side=info_side,
    )
    card = models.RecipeCard.create(
        filepath=str(filepath),
        template=template.template_name,
        recipe_id=recipe.pk,
        image_id=background_image.pk if background_image is not None else None,
    )
    events.publish_event(
        event_type=events.RECIPE_CARD_CREATED,
        recipe_id=recipe.pk,
        card_id=card.pk,
        template=template.template_name,
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
