from __future__ import annotations

import uuid
from pathlib import Path

import piexif  # type: ignore[import-untyped]
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFilter, ImageFont

import qrcode  # type: ignore[import-untyped]
import qrcode.image.pil  # type: ignore[import-untyped]

from src.data import models
from src.domain.images import events
from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import templates as card_templates

_QR_SIZE = 300
_QR_MARGIN = 20
_BLUR_RADIUS = 12
_PANEL_ALPHA = 140  # 0-255 opacity of the text-readability overlay panel
_TEXT_PADDING = 40
_LINE_HEIGHT = 44
_FONT_SIZE = 28
_TITLE_FONT_SIZE = 34
_TITLE_LINE_HEIGHT = 56
_LABEL_COLOR = (220, 220, 220)
_VALUE_COLOR = (255, 255, 255)

# Gradient colours (dark teal → dark indigo)
_GRADIENT_TOP = (18, 52, 64)
_GRADIENT_BOTTOM = (30, 20, 70)


def _cover_fill(img: PILImage.Image, target_w: int, target_h: int) -> PILImage.Image:
    """Scale *img* so it fills (target_w × target_h) with no empty space, then center-crop."""
    scale = max(target_w / img.width, target_h / img.height)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def _build_gradient(width: int, height: int) -> PILImage.Image:
    """Return a soft vertical gradient from _GRADIENT_TOP to _GRADIENT_BOTTOM."""
    img = PILImage.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    r0, g0, b0 = _GRADIENT_TOP
    r1, g1, b1 = _GRADIENT_BOTTOM
    for y in range(height):
        t = y / (height - 1)
        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _embed_recipe_exif(*, filepath: Path, json_str: str) -> None:
    """Embed recipe JSON into the UserComment EXIF field of the saved JPEG at filepath."""
    exif_bytes = piexif.dump({
        "Exif": {
            piexif.ExifIFD.UserComment: b"ASCII\x00\x00\x00" + json_str.encode("ascii"),
        }
    })
    piexif.insert(exif_bytes, str(filepath))


def _compose_card(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
) -> tuple[PILImage.Image, str, bool]:
    """Build the card PIL image. Returns (canvas, json_str, use_gradient)."""
    target_w, target_h = template.output_size
    if background_image is None:
        canvas = _build_gradient(target_w, target_h)
    else:
        with PILImage.open(background_image.filepath) as img:
            canvas = _cover_fill(img.convert("RGB"), target_w, target_h)
        if template.background_effect == "blur":
            canvas = canvas.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))

    panel_w = target_w // 2
    overlay = PILImage.new("RGBA", (panel_w, target_h), (0, 0, 0, _PANEL_ALPHA))
    canvas_rgba = canvas.convert("RGBA")
    canvas_rgba.paste(overlay, (0, 0), overlay)
    canvas = canvas_rgba.convert("RGB")

    draw = ImageDraw.Draw(canvas)
    label_font = _load_font(_FONT_SIZE)
    value_font = _load_font(_FONT_SIZE)
    lines = card_queries.get_recipe_cover_lines(recipe=recipe, template=template)
    x = _TEXT_PADDING
    y = _TEXT_PADDING
    if recipe.name:
        title_font = _load_font(_TITLE_FONT_SIZE)
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
    qr_img = qrcode.make(json_str)
    qr_img = qr_img.resize((_QR_SIZE, _QR_SIZE), PILImage.Resampling.LANCZOS)
    qr_pos = (target_w - _QR_SIZE - _QR_MARGIN, target_h - _QR_SIZE - _QR_MARGIN)
    canvas.paste(qr_img, qr_pos)

    return canvas, json_str, background_image is None


def _save_card(
    *,
    canvas: PILImage.Image,
    filepath: Path,
    json_str: str,
    use_gradient: bool,
) -> None:
    canvas.save(str(filepath), format="JPEG", quality=90)
    if use_gradient:
        _embed_recipe_exif(filepath=filepath, json_str=json_str)


def preview_recipe_card_image(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_path: Path,
) -> Path:
    """Compose a recipe card image and save it to output_path. Return output_path.

    Intended for previews: the caller controls the exact output path (e.g. a
    deterministic /tmp/ path) so successive previews for the same options
    overwrite the previous file rather than accumulating.
    """
    canvas, json_str, use_gradient = _compose_card(
        recipe=recipe, template=template, background_image=background_image,
    )
    _save_card(canvas=canvas, filepath=output_path, json_str=json_str, use_gradient=use_gradient)
    return output_path


def create_recipe_card_image(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_dir: Path,
) -> Path:
    """Compose a recipe card image and save it to output_dir. Return the file path.

    If background_image is given, resizes/crops it to template.output_size and
    applies Gaussian blur when template.background_effect == "blur".
    If background_image is None, generates a soft gradient background and embeds
    the recipe JSON into the EXIF UserComment so the card can be re-imported.
    """
    canvas, json_str, use_gradient = _compose_card(
        recipe=recipe, template=template, background_image=background_image,
    )
    filepath = output_dir / f"recipe_{recipe.pk}_{uuid.uuid4().hex[:8]}.jpg"
    _save_card(canvas=canvas, filepath=filepath, json_str=json_str, use_gradient=use_gradient)
    return filepath


def create_recipe_card(
    *,
    recipe: models.FujifilmRecipe,
    template: card_templates.CardTemplate,
    background_image: models.Image | None,
    output_dir: Path,
) -> models.RecipeCard:
    """Create a recipe card image, persist a RecipeCard record, and publish an event.

    Calls create_recipe_card_image internally, then saves a RecipeCard to the DB
    and publishes a recipe.card.created event.
    """
    filepath = create_recipe_card_image(
        recipe=recipe,
        template=template,
        background_image=background_image,
        output_dir=output_dir,
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
