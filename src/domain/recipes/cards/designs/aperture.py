from __future__ import annotations

from typing import ClassVar

import attrs
from PIL import Image as PILImage
from PIL import ImageDraw, ImageEnhance, ImageFilter, ImageFont

from django import conf

from src.data import models
from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import rendering
from src.domain.recipes.cards.designs import base

_SIZE = (1080, 1920)
_CONTENT_X = 56
_CONTENT_W = 968  # 1080 - 56 - 56
_MARGIN_TOP = 48
_MARGIN_BOTTOM = 30

# Real minus sign (U+2212) for negative values, per the design spec.
_MINUS = "−"

# Background: blurred, lightly darkened but saturation-boosted photo with a
# top->bottom black scrim (matches the design's blur/brightness/saturate).
# The scrim's top/bottom opacity is configurable via settings (percentages).
_BG_BLUR = 64
_BG_BRIGHTNESS = 0.78
_BG_SATURATION = 1.25
_SCRIM_COLOR = (10, 11, 15)


def _scrim_alpha(percent: int) -> int:
    return round(max(0, min(100, percent)) / 100 * 255)

_WHITE = (255, 255, 255)
_EYEBROW_COLOR = (170, 174, 182)
_HERO_LABEL_COLOR = (168, 172, 180)
_GRID_LABEL_COLOR = (163, 167, 176)
_IMPORT_LABEL_COLOR = (204, 208, 216)
_WB_RED = (255, 107, 107)
_WB_BLUE = (107, 168, 255)
_WORDMARK_FILM = (239, 68, 68)
_WORDMARK_CASE = (241, 245, 249)

# Header
_EYEBROW_SIZE = 24
_EYEBROW_TRACKING = 2
_TITLE_SIZE = 52
_TITLE_TRACKING = -2
_EYEBROW_TO_TITLE = 6
_TITLE_TO_HERO = 20

# Hero photo (native 3:2, full content width)
_HERO_H = 645  # 968 * 2 / 3
_HERO_RADIUS = 26
_HERO_TO_TILES = 12

# Hero tiles (Film Simulation + White Balance)
_HERO_TILE_GAP = 14
_HERO_TILE_H = 104
_HERO_TILE_RADIUS = 20
_HERO_TILE_FILL = (255, 255, 255, 26)
_HERO_TILE_BORDER = (255, 255, 255, 41)
_HERO_TILE_PAD_X = 22
_HERO_TILE_PAD_Y = 13
_HERO_SIM_FLEX = 1.4
_HERO_WB_FLEX = 1.0
_HERO_LABEL_SIZE = 22
_HERO_LABEL_TRACKING = 1.5
_HERO_VALUE_SIZE = 36
_HERO_VALUE_TRACKING = -1
_WB_SHIFT_SIZE = 26
_HERO_TILES_TO_GRID = 10

# Parameter grid (3 columns)
_GRID_COLS = 3
_GRID_GAP = 12
_GRID_TILE_H = 96
_GRID_TILE_RADIUS = 16
_GRID_TILE_FILL = (255, 255, 255, 20)
_GRID_TILE_BORDER = (255, 255, 255, 33)
_GRID_PAD_X = 18
_GRID_PAD_Y = 13
_GRID_LABEL_SIZE = 20
_GRID_LABEL_TRACKING = 1
_GRID_VALUE_SIZE = 30
_GRID_VALUE_TRACKING = -0.5

# Import module
_IMPORT_BAR_RADIUS = 22
_IMPORT_BAR_FILL = (255, 255, 255, 20)
_IMPORT_BAR_BORDER = (255, 255, 255, 33)
_IMPORT_BAR_PAD = 18
_IMPORT_LABEL_SIZE = 21
_IMPORT_LABEL_TRACKING = 3
_IMPORT_LABEL_TO_PILL = 14
_WORDMARK_SIZE = 30
_PILL_RADIUS = 14
_PILL_PAD_X = 24
_PILL_PAD_Y = 14
_LOGO_H = 200

# Grid field order. Hidden/inapplicable fields are dropped by the query.
_GRID_FIELDS_COLOR: tuple[str, ...] = (
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
_GRID_FIELDS_BW: tuple[str, ...] = (
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


def _line_height(font: ImageFont.FreeTypeFont) -> int:
    ascent, descent = font.getmetrics()
    return ascent + descent


def _frosted_tile(
    size: tuple[int, int],
    *,
    radius: int,
    fill: rendering.RGBAColor,
    border: rendering.RGBAColor,
) -> PILImage.Image:
    tile = PILImage.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle(
        [(0, 0), (size[0] - 1, size[1] - 1)],
        radius=radius,
        fill=fill,
        outline=border,
        width=1,
    )
    return tile


def _vertical_scrim(
    size: tuple[int, int],
    color: rendering.RGBColor,
    alpha_top: int,
    alpha_bottom: int,
) -> PILImage.Image:
    width, height = size
    column = PILImage.new("RGBA", (1, height))
    for y in range(height):
        alpha = int(alpha_top + (alpha_bottom - alpha_top) * y / (height - 1))
        column.putpixel((0, y), (*color, alpha))
    return column.resize((width, height))


@attrs.frozen
class ApertureDesign(base.CardDesign):
    """
    A dark, story-format (9:16) card: a blurred photo background, a hero photo,
    frosted-glass parameter tiles, and a bottom import module with the logo + QR.
    """

    output_size: ClassVar[tuple[int, int]] = _SIZE
    requires_background_image: ClassVar[bool] = True

    @property
    def template_name(self) -> str:
        return "aperture"

    def render(
        self,
        *,
        recipe: models.FujifilmRecipe,
        background_image: models.Image | None,
    ) -> rendering.RenderedCard:
        canvas = self._build_background(background_image)
        draw = ImageDraw.Draw(canvas)

        y = self._draw_header(canvas, draw, recipe, _MARGIN_TOP)
        if background_image is not None:
            with PILImage.open(background_image.filepath) as photo:
                hero = rendering.cover_fill(photo.convert("RGB"), _CONTENT_W, _HERO_H)
            rendering.paste_rounded(canvas, hero, (_CONTENT_X, y), _HERO_RADIUS)
            y += _HERO_H
        y += _HERO_TO_TILES
        y = self._draw_hero_tiles(canvas, draw, recipe, y)
        y += _HERO_TILES_TO_GRID
        self._draw_grid(canvas, draw, recipe, y)

        self._draw_import_module(canvas, draw, recipe)

        json_str = card_queries.get_recipe_as_json(recipe=recipe)
        return rendering.RenderedCard(
            canvas=canvas.convert("RGB"),
            json_str=json_str,
            embed_exif=background_image is None,
        )

    def _build_background(self, background_image: models.Image | None) -> PILImage.Image:
        width, height = _SIZE
        if background_image is None:
            base_img = rendering.build_gradient(width, height).convert("RGBA")
        else:
            with PILImage.open(background_image.filepath) as img:
                filled = rendering.cover_fill(img.convert("RGB"), width, height)
            blurred = filled.filter(ImageFilter.GaussianBlur(_BG_BLUR))
            saturated = ImageEnhance.Color(blurred).enhance(_BG_SATURATION)
            darkened = ImageEnhance.Brightness(saturated).enhance(_BG_BRIGHTNESS)
            base_img = darkened.convert("RGBA")
        scrim = _vertical_scrim(
            (width, height),
            _SCRIM_COLOR,
            _scrim_alpha(conf.settings.RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY),
            _scrim_alpha(conf.settings.RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY),
        )
        base_img.alpha_composite(scrim)
        return base_img

    def _eyebrow_text(self, recipe: models.FujifilmRecipe) -> str:
        parts = ["FILM RECIPE"]
        if card_queries.is_monochromatic(recipe):
            parts.append("B&W")
        sensors = card_queries.get_sensor_names(recipe)
        if sensors:
            parts.append(", ".join(sensors))
        return " · ".join(parts).upper()

    def _draw_header(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        top: int,
    ) -> int:
        eyebrow_font = rendering.load_space_mono(_EYEBROW_SIZE)
        rendering.draw_tracked_text(
            draw,
            (_CONTENT_X, top),
            self._eyebrow_text(recipe),
            font=eyebrow_font,
            fill=_EYEBROW_COLOR,
            tracking=_EYEBROW_TRACKING,
        )
        y = top + _line_height(eyebrow_font) + _EYEBROW_TO_TITLE
        title_font = rendering.load_archivo(_TITLE_SIZE, weight=800)
        rendering.draw_tracked_text(
            draw,
            (_CONTENT_X, y),
            recipe.name or recipe.film_simulation,
            font=title_font,
            fill=_WHITE,
            tracking=_TITLE_TRACKING,
        )
        return y + _line_height(title_font) + _TITLE_TO_HERO

    def _draw_hero_tiles(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        top: int,
    ) -> int:
        flex_total = _HERO_SIM_FLEX + _HERO_WB_FLEX
        available = _CONTENT_W - _HERO_TILE_GAP
        sim_w = int(available * _HERO_SIM_FLEX / flex_total)
        wb_w = _CONTENT_W - _HERO_TILE_GAP - sim_w

        label_font = rendering.load_space_mono(_HERO_LABEL_SIZE)
        value_font = rendering.load_archivo(_HERO_VALUE_SIZE, weight=800)
        shift_font = rendering.load_space_mono(_WB_SHIFT_SIZE, bold=True)

        # Values and the WB shift share one baseline so R/B line up with the
        # value text (matching the design's align-items: baseline).
        ly = top + _HERO_TILE_PAD_Y
        vy = ly + _line_height(label_font) + 4
        value_baseline = vy + value_font.getmetrics()[0]

        # Film Simulation tile.
        self._frosted(canvas, (_CONTENT_X, top), (sim_w, _HERO_TILE_H), _HERO_TILE_RADIUS, _HERO_TILE_FILL, _HERO_TILE_BORDER)
        lx = _CONTENT_X + _HERO_TILE_PAD_X
        rendering.draw_tracked_text(draw, (lx, ly), "FILM SIMULATION", font=label_font, fill=_HERO_LABEL_COLOR, tracking=_HERO_LABEL_TRACKING)
        rendering.draw_tracked_text(draw, (lx, value_baseline), recipe.film_simulation, font=value_font, fill=_WHITE, tracking=_HERO_VALUE_TRACKING, anchor="ls")

        # White Balance tile.
        wb_x = _CONTENT_X + sim_w + _HERO_TILE_GAP
        self._frosted(canvas, (wb_x, top), (wb_w, _HERO_TILE_H), _HERO_TILE_RADIUS, _HERO_TILE_FILL, _HERO_TILE_BORDER)
        wlx = wb_x + _HERO_TILE_PAD_X
        rendering.draw_tracked_text(draw, (wlx, ly), "WHITE BALANCE", font=label_font, fill=_HERO_LABEL_COLOR, tracking=_HERO_LABEL_TRACKING)
        end_x = rendering.draw_tracked_text(draw, (wlx, value_baseline), recipe.white_balance, font=value_font, fill=_WHITE, tracking=_HERO_VALUE_TRACKING, anchor="ls")
        shift_x = end_x + 14
        red = _display_value(f"R {recipe.white_balance_red:+d}")
        blue = _display_value(f"B {recipe.white_balance_blue:+d}")
        red_end = rendering.draw_tracked_text(draw, (shift_x, value_baseline), red, font=shift_font, fill=_WB_RED, anchor="ls")
        rendering.draw_tracked_text(draw, (red_end + 12, value_baseline), blue, font=shift_font, fill=_WB_BLUE, anchor="ls")

        return top + _HERO_TILE_H

    def _draw_grid(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
        top: int,
    ) -> None:
        fields = _GRID_FIELDS_BW if card_queries.is_monochromatic(recipe) else _GRID_FIELDS_COLOR
        tiles = card_queries.get_recipe_field_lines(recipe=recipe, fields=fields, label_style="long")
        label_font = rendering.load_space_mono(_GRID_LABEL_SIZE)
        value_font = rendering.load_archivo(_GRID_VALUE_SIZE, weight=800)
        cell_w = (_CONTENT_W - (_GRID_COLS - 1) * _GRID_GAP) // _GRID_COLS

        for index, line in enumerate(tiles):
            row, col = divmod(index, _GRID_COLS)
            x = _CONTENT_X + col * (cell_w + _GRID_GAP)
            y = top + row * (_GRID_TILE_H + _GRID_GAP)
            self._frosted(canvas, (x, y), (cell_w, _GRID_TILE_H), _GRID_TILE_RADIUS, _GRID_TILE_FILL, _GRID_TILE_BORDER)
            lx = x + _GRID_PAD_X
            ly = y + _GRID_PAD_Y
            rendering.draw_tracked_text(draw, (lx, ly), line.label.upper(), font=label_font, fill=_GRID_LABEL_COLOR, tracking=_GRID_LABEL_TRACKING)
            vy = ly + _line_height(label_font) + 2
            rendering.draw_tracked_text(draw, (lx, vy), _display_value(line.value), font=value_font, fill=_WHITE, tracking=_GRID_VALUE_TRACKING)

    def _draw_import_module(
        self,
        canvas: PILImage.Image,
        draw: ImageDraw.ImageDraw,
        recipe: models.FujifilmRecipe,
    ) -> None:
        label_font = rendering.load_space_mono(_IMPORT_LABEL_SIZE, bold=True)
        wordmark_font = rendering.load_archivo(_WORDMARK_SIZE, weight=900)
        qr = rendering.make_qr(card_queries.get_recipe_as_json(recipe=recipe)).convert("RGB")
        with PILImage.open(rendering.STACKED_LOGO_PATH) as logo_src:
            logo_rgba = logo_src.convert("RGBA")
        logo_w = int(_LOGO_H * logo_rgba.width / logo_rgba.height)
        logo = logo_rgba.resize((logo_w, _LOGO_H), PILImage.Resampling.LANCZOS)

        pill_content_w = logo_w + qr.width
        pill_w = pill_content_w + _PILL_PAD_X * 2
        pill_h = max(_LOGO_H, qr.height) + _PILL_PAD_Y * 2

        label = "IMPORT RECIPE WITH "
        label_w = self._tracked_width(draw, label, label_font, _IMPORT_LABEL_TRACKING)
        wordmark_w = self._tracked_width(draw, "filmcase", wordmark_font, 0)
        label_row_w = label_w + wordmark_w
        label_row_h = max(_line_height(label_font), _line_height(wordmark_font))

        bar_content_w = max(pill_w, label_row_w)
        bar_w = bar_content_w + _IMPORT_BAR_PAD * 2
        bar_h = _IMPORT_BAR_PAD * 2 + label_row_h + _IMPORT_LABEL_TO_PILL + pill_h
        bar_x = (_SIZE[0] - bar_w) // 2
        bar_y = _SIZE[1] - _MARGIN_BOTTOM - bar_h

        self._frosted(canvas, (bar_x, bar_y), (bar_w, bar_h), _IMPORT_BAR_RADIUS, _IMPORT_BAR_FILL, _IMPORT_BAR_BORDER)

        # Centered label row: mono label + coloured wordmark.
        label_x = bar_x + (bar_w - label_row_w) // 2
        label_y = bar_y + _IMPORT_BAR_PAD
        end_x = rendering.draw_tracked_text(draw, (label_x, label_y), label, font=label_font, fill=_IMPORT_LABEL_COLOR, tracking=_IMPORT_LABEL_TRACKING)
        rendering.draw_filmcase_wordmark(draw, (end_x, label_y), font=wordmark_font, film_color=_WORDMARK_FILM, case_color=_WORDMARK_CASE)

        # White pill holding the logo + QR couple.
        pill_x = bar_x + (bar_w - pill_w) // 2
        pill_y = label_y + label_row_h + _IMPORT_LABEL_TO_PILL
        pill = PILImage.new("RGBA", (pill_w, pill_h), (0, 0, 0, 0))
        ImageDraw.Draw(pill).rounded_rectangle(
            [(0, 0), (pill_w - 1, pill_h - 1)], radius=_PILL_RADIUS, fill=(255, 255, 255, 255)
        )
        pill.alpha_composite(logo, (_PILL_PAD_X, (pill_h - _LOGO_H) // 2))
        pill.paste(qr, (_PILL_PAD_X + logo_w, (pill_h - qr.height) // 2))
        canvas.alpha_composite(pill, (pill_x, pill_y))

    def _frosted(
        self,
        canvas: PILImage.Image,
        position: tuple[int, int],
        size: tuple[int, int],
        radius: int,
        fill: rendering.RGBAColor,
        border: rendering.RGBAColor,
    ) -> None:
        canvas.alpha_composite(_frosted_tile(size, radius=radius, fill=fill, border=border), position)

    def _tracked_width(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        tracking: float,
    ) -> int:
        return int(sum(draw.textlength(char, font=font) + tracking for char in text))
