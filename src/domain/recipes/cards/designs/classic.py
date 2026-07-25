from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal

import attrs
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFilter

from src.data import models
from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import rendering
from src.domain.recipes.cards.designs import base

LabelStyle = Literal["long", "short"]
BackgroundEffect = Literal["none", "blur"]
InfoSide = Literal["left", "right"]

DEFAULT_INFO_SIDE: InfoSide = "left"

_OUTPUT_SIZE = (1080, 1080)
_QR_MARGIN = 20
_PANEL_ALPHA = 140  # 0-255 opacity of the text-readability overlay panel
_TEXT_PADDING = 40
_LINE_HEIGHT = 44
_FONT_SIZE = 28
_TITLE_FONT_SIZE = 34
_TITLE_LINE_HEIGHT = 56
_LABEL_COLOR = (220, 220, 220)
_VALUE_COLOR = (255, 255, 255)
_LOGO_PATH = Path(__file__).resolve().parents[4] / "interfaces" / "static" / "images" / "filmcase_stacked_full.png"
_LOGO_WIDTH = 320
_LOGO_PADDING = 20


@attrs.frozen
class ClassicDesign(base.CardDesign):
    """
    The original square recipe card: a photo (or gradient) background with a
    half-canvas info panel and a QR code in the opposite bottom corner.

    The four legacy templates (long/short labels x blur/sharp background) are
    the four combinations of this one design's options, so their persisted
    ``template_name`` strings are reproduced exactly for backward compatibility.
    """

    label_style: LabelStyle = "long"
    background_effect: BackgroundEffect = "blur"
    info_side: InfoSide = DEFAULT_INFO_SIDE

    output_size: ClassVar[tuple[int, int]] = _OUTPUT_SIZE
    requires_background_image: ClassVar[bool] = False

    @property
    def template_name(self) -> str:
        style = "long" if self.label_style == "long" else "short"
        suffix = "_sharp" if self.background_effect == "none" else ""
        return f"{style}_label{suffix}"

    def render(
        self,
        *,
        recipe: models.FujifilmRecipe,
        background_image: models.Image | None,
    ) -> rendering.RenderedCard:
        target_w, target_h = self.output_size
        if background_image is None:
            canvas = rendering.build_gradient(target_w, target_h)
        else:
            with PILImage.open(background_image.filepath) as img:
                canvas = rendering.cover_fill(img.convert("RGB"), target_w, target_h)
            if self.background_effect == "blur":
                canvas = canvas.filter(ImageFilter.GaussianBlur(radius=rendering.BLUR_RADIUS))

        panel_w = target_w // 2
        panel_x = 0 if self.info_side == "left" else target_w - panel_w
        overlay = PILImage.new("RGBA", (panel_w, target_h), (0, 0, 0, _PANEL_ALPHA))
        canvas_rgba = canvas.convert("RGBA")
        canvas_rgba.paste(overlay, (panel_x, 0), overlay)
        canvas = canvas_rgba.convert("RGB")

        draw = ImageDraw.Draw(canvas)
        label_font = rendering.load_font(_FONT_SIZE)
        value_font = rendering.load_font(_FONT_SIZE)
        lines = card_queries.get_recipe_cover_lines(recipe=recipe, label_style=self.label_style)
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
        qr_x = _QR_MARGIN if self.info_side == "right" else target_w - rendering.QR_SIZE - _QR_MARGIN
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
            white_bg = PILImage.new(
                "RGBA",
                (_LOGO_WIDTH + _LOGO_PADDING * 2, content_h + _LOGO_PADDING * 2),
                (255, 255, 255, 255),
            )
            canvas_rgba = canvas.convert("RGBA")
            canvas_rgba.paste(white_bg, (logo_x - _LOGO_PADDING, logo_y - _LOGO_PADDING))
            canvas_rgba.paste(logo, (logo_x, logo_y), logo)
            canvas = canvas_rgba.convert("RGB")

        return rendering.RenderedCard(
            canvas=canvas,
            json_str=json_str,
            embed_exif=background_image is None,
        )
