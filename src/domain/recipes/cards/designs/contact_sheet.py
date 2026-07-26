from __future__ import annotations

from typing import ClassVar

import attrs
from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageFilter, ImageFont

from src.data import models
from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import rendering
from src.domain.recipes.cards.designs import base

_SIZE = (1080, 1920)
_MINUS = "−"

# Blurred, lightly darkened photo frame behind the paper panel.
_BG_BLUR = 60
_BG_BRIGHTNESS = 0.85
_SCRIM = (20, 22, 28, int(0.28 * 255))

# Paper panel
_PANEL_INSET = 26
_PANEL_RADIUS = 30
_PAD_L = 48
_PAD_R = 48
_PAD_T = 44
_PAD_B = 40

_PAPER = (247, 246, 243)
_INK = (17, 24, 39)
_RED = (239, 68, 68)
_HAIRLINE = (228, 226, 220)
_MUTED_LABEL = (125, 130, 140)
_EYEBROW = (138, 143, 153)

# Header
_ACCENT_W = 8
_ACCENT_H = 44
_ACCENT_RADIUS = 2
_ACCENT_GAP = 16
_EYEBROW_SIZE = 22
_EYEBROW_TRACKING = 2
_TITLE_SIZE = 50
_TITLE_TRACKING = -1.5
_EYEBROW_TO_TITLE = 4
_HEADER_TO_HERO = 24

# Hero photo
_HERO_RADIUS = 20
_HERO_TO_ROWS = 22

# Two-column key/value rows
_ROW_COLS = 2
_ROW_COL_GAP = 52
_ROW_PAD_Y = 11
_ROW_LABEL_SIZE = 22
_ROW_LABEL_TRACKING = 0.5
_ROW_VALUE_SIZE = 27

# Import module
_IMPORT_TOP_GAP = 16
_IMPORT_LABEL_SIZE = 21
_IMPORT_LABEL_TRACKING = 3
_IMPORT_LABEL_TO_COUPLE = 10
_WORDMARK_SIZE = 27
_LOGO_H = 196

_PARAMETER_FIELDS_COLOR: tuple[str, ...] = (
    "grain_roughness",
    "grain_size",
    "dynamic_range",
    "d_range_priority",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "highlight",
    "shadow",
    "color",
    "sharpness",
    "high_iso_nr",
    "clarity",
)
_PARAMETER_FIELDS_BW: tuple[str, ...] = (
    "grain_roughness",
    "grain_size",
    "dynamic_range",
    "d_range_priority",
    "color_chrome_effect",
    "color_chrome_fx_blue",
    "monochromatic_color_warm_cool",
    "monochromatic_color_magenta_green",
    "highlight",
    "shadow",
    "sharpness",
    "high_iso_nr",
    "clarity",
)


def _display_value(value: str) -> str:
    return value.replace("-", _MINUS)


@attrs.frozen
class ContactSheetDesign(base.CardDesign):
    """
    A light "paper" spec-sheet card (1080x1920): a blurred photo frame behind a
    paper panel that holds the header, hero photo, a two-column key/value list of
    every parameter, and a hairline-separated import module with the logo + QR.
    """

    output_size: ClassVar[tuple[int, int]] = _SIZE
    requires_background_image: ClassVar[bool] = True

    @property
    def template_name(self) -> str:
        return "contact_sheet"

    def render(
        self,
        *,
        recipe: models.FujifilmRecipe,
        background_photo_path: str | None,
    ) -> rendering.RenderedCard:
        canvas = self._build_background(background_photo_path)
        draw = ImageDraw.Draw(canvas)

        panel_x = _PANEL_INSET
        panel_w = _SIZE[0] - _PANEL_INSET * 2
        content_x = panel_x + _PAD_L
        content_w = panel_w - _PAD_L - _PAD_R
        self._draw_panel(canvas)

        y = self._draw_header(canvas, draw, recipe, content_x, _PANEL_INSET + _PAD_T)
        y += _HEADER_TO_HERO
        if background_photo_path is not None:
            hero_h = content_w * 2 // 3
            with PILImage.open(background_photo_path) as photo:
                hero = rendering.cover_fill(photo.convert("RGB"), content_w, hero_h)
            rendering.paste_rounded(canvas, hero, (content_x, y), _HERO_RADIUS)
            y += hero_h
        y += _HERO_TO_ROWS
        self._draw_rows(draw, recipe, content_x, content_w, y)

        self._draw_import_module(canvas, draw, recipe, content_x, content_w)

        json_str = card_queries.get_recipe_as_json(recipe=recipe)
        return rendering.RenderedCard(
            canvas=canvas.convert("RGB"),
            json_str=json_str,
            embed_exif=background_photo_path is None,
        )

    def _build_background(self, background_photo_path: str | None) -> PILImage.Image:
        width, height = _SIZE
        if background_photo_path is None:
            base_img = rendering.build_gradient(width, height).convert("RGBA")
        else:
            with PILImage.open(background_photo_path) as img:
                filled = rendering.cover_fill(img.convert("RGB"), width, height)
            blurred = filled.filter(ImageFilter.GaussianBlur(_BG_BLUR))
            base_img = ImageEnhance.Brightness(blurred).enhance(_BG_BRIGHTNESS).convert("RGBA")
        scrim = PILImage.new("RGBA", (width, height), _SCRIM)
        base_img.alpha_composite(scrim)
        return base_img

    def _draw_panel(self, canvas: PILImage.Image) -> None:
        x0 = _PANEL_INSET
        y0 = _PANEL_INSET
        x1 = _SIZE[0] - _PANEL_INSET
        y1 = _SIZE[1] - _PANEL_INSET
        ImageDraw.Draw(canvas).rounded_rectangle(
            [(x0, y0), (x1 - 1, y1 - 1)], radius=_PANEL_RADIUS, fill=(*_PAPER, 255)
        )

    def _draw_header(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        content_x: int,
        top: int,
    ) -> int:
        eyebrow_font = rendering.load_space_mono(_EYEBROW_SIZE)
        title_font = rendering.load_archivo(_TITLE_SIZE, weight=800)
        block_h = rendering.line_height(eyebrow_font) + _EYEBROW_TO_TITLE + rendering.line_height(title_font)

        accent_y = top + (block_h - _ACCENT_H) // 2
        draw.rounded_rectangle(
            [(content_x, accent_y), (content_x + _ACCENT_W, accent_y + _ACCENT_H)],
            radius=_ACCENT_RADIUS,
            fill=_RED,
        )

        text_x = content_x + _ACCENT_W + _ACCENT_GAP
        rendering.draw_tracked_text(
            draw, (text_x, top), self._eyebrow_text(recipe),
            font=eyebrow_font, fill=_EYEBROW, tracking=_EYEBROW_TRACKING,
        )
        title_y = top + rendering.line_height(eyebrow_font) + _EYEBROW_TO_TITLE
        rendering.draw_tracked_text(
            draw, (text_x, title_y), recipe.name or recipe.film_simulation,
            font=title_font, fill=_INK, tracking=_TITLE_TRACKING,
        )
        return top + block_h

    def _eyebrow_text(self, recipe: models.FujifilmRecipe) -> str:
        parts = ["FILM RECIPE"]
        if card_queries.is_monochromatic(recipe):
            parts.append("B&W")
        return " · ".join(parts).upper()

    def _rows(self, recipe: models.FujifilmRecipe) -> list[tuple[str, str]]:
        sensors = card_queries.get_sensor_names(recipe)
        red = _display_value(f"{recipe.white_balance_red:+d}")
        blue = _display_value(f"{recipe.white_balance_blue:+d}")
        rows: list[tuple[str, str]] = [
            ("Film Simulation", recipe.film_simulation),
            ("Sensors", ", ".join(sensors) if sensors else "—"),
            ("White Balance", recipe.white_balance),
            ("WB Shift", f"R {red} · B {blue}"),
        ]
        fields = _PARAMETER_FIELDS_BW if card_queries.is_monochromatic(recipe) else _PARAMETER_FIELDS_COLOR
        for line in card_queries.get_recipe_field_lines(recipe=recipe, fields=fields, label_style="long"):
            rows.append((line.label, _display_value(line.value)))
        return rows

    def _draw_rows(
        self,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        content_x: int,
        content_w: int,
        top: int,
    ) -> None:
        rows = self._rows(recipe)
        label_font = rendering.load_space_mono(_ROW_LABEL_SIZE)
        value_font = rendering.load_archivo(_ROW_VALUE_SIZE, weight=700)
        col_w = (content_w - _ROW_COL_GAP) // _ROW_COLS
        row_h = _ROW_PAD_Y * 2 + rendering.line_height(value_font)
        baseline_offset = _ROW_PAD_Y + value_font.getmetrics()[0]

        for index, (label, value) in enumerate(rows):
            col = index % _ROW_COLS
            grid_row = index // _ROW_COLS
            cell_x = content_x + col * (col_w + _ROW_COL_GAP)
            cell_y = top + grid_row * row_h
            baseline = cell_y + baseline_offset
            rendering.draw_tracked_text(
                draw, (cell_x, baseline), label.upper(),
                font=label_font, fill=_MUTED_LABEL, tracking=_ROW_LABEL_TRACKING, anchor="ls",
            )
            draw.text((cell_x + col_w, baseline), value, font=value_font, fill=_INK, anchor="rs")
            hairline_y = cell_y + row_h - 1
            draw.line([(cell_x, hairline_y), (cell_x + col_w, hairline_y)], fill=_HAIRLINE, width=1)

    def _draw_import_module(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        content_x: int,
        content_w: int,
    ) -> None:
        label_font = rendering.load_space_mono(_IMPORT_LABEL_SIZE, bold=True)
        wordmark_font = rendering.load_archivo(_WORDMARK_SIZE, weight=900)
        qr = rendering.make_qr(card_queries.get_recipe_as_json(recipe=recipe)).convert("RGB")
        with PILImage.open(rendering.STACKED_LOGO_PATH) as logo_src:
            logo_rgba = logo_src.convert("RGBA")
        logo_w = int(_LOGO_H * logo_rgba.width / logo_rgba.height)
        logo = logo_rgba.resize((logo_w, _LOGO_H), PILImage.Resampling.LANCZOS)

        label = "IMPORT RECIPE WITH "
        label_w = self._tracked_width(draw, label, label_font, _IMPORT_LABEL_TRACKING)
        wordmark_w = self._tracked_width(draw, "filmcase", wordmark_font, 0)
        label_h = max(rendering.line_height(label_font), rendering.line_height(wordmark_font))
        couple_w = logo_w + qr.width
        couple_h = max(_LOGO_H, qr.height)

        module_h = label_h + _IMPORT_LABEL_TO_COUPLE + couple_h
        content_bottom = _SIZE[1] - _PANEL_INSET - _PAD_B
        top = content_bottom - module_h

        # Full-width hairline separating the module from the rows above.
        draw.line(
            [(content_x, top - _IMPORT_TOP_GAP), (content_x + content_w, top - _IMPORT_TOP_GAP)],
            fill=_HAIRLINE,
            width=1,
        )

        # Centered label row.
        label_x = content_x + (content_w - (label_w + wordmark_w)) // 2
        end_x = rendering.draw_tracked_text(
            draw, (label_x, top), label, font=label_font, fill=_MUTED_LABEL, tracking=_IMPORT_LABEL_TRACKING,
        )
        rendering.draw_filmcase_wordmark(draw, (end_x, top), font=wordmark_font, film_color=_RED, case_color=_INK)

        # Logo + QR couple, centered, directly on the paper (no pill).
        couple_x = content_x + (content_w - couple_w) // 2
        couple_y = top + label_h + _IMPORT_LABEL_TO_COUPLE
        canvas.alpha_composite(logo, (couple_x, couple_y + (couple_h - _LOGO_H) // 2))
        canvas.paste(qr, (couple_x + logo_w, couple_y + (couple_h - qr.height) // 2))

    def _tracked_width(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        tracking: float,
    ) -> int:
        return int(sum(draw.textlength(char, font=font) + tracking for char in text))
