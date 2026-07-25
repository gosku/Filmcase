from __future__ import annotations

from pathlib import Path

import attrs
import piexif  # type: ignore[import-untyped]
from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

import qrcode  # type: ignore[import-untyped]
import qrcode.image.pil  # type: ignore[import-untyped]


# The QR code is a shared global across every card design: the same size and
# specs are used everywhere so any reader scans a card reliably regardless of
# which design produced it.
QR_SIZE = 300

# Softening radius applied to a photo background when a design blurs it.
BLUR_RADIUS = 12

# Gradient colours for the no-photo fallback background (dark teal -> dark indigo).
GRADIENT_TOP = (18, 52, 64)
GRADIENT_BOTTOM = (30, 20, 70)

# Prefix piexif writes before the payload when embedding recipe JSON.
_EXIF_ASCII_PREFIX = b"ASCII\x00\x00\x00"

_STATIC_DIR = Path(__file__).resolve().parents[3] / "interfaces" / "static"
FONTS_DIR = _STATIC_DIR / "fonts"
ARCHIVO_PATH = FONTS_DIR / "Archivo-VariableFont_wdth,wght.ttf"
SPACE_MONO_REGULAR_PATH = FONTS_DIR / "SpaceMono-Regular.ttf"
SPACE_MONO_BOLD_PATH = FONTS_DIR / "SpaceMono-Bold.ttf"
STACKED_LOGO_PATH = _STATIC_DIR / "images" / "original-branding" / "filmcase_stacked_tight.png"

# Archivo is a variable font. FreeType reports its axes in the order
# [Weight, Width]; we always render at the normal width.
_ARCHIVO_NORMAL_WIDTH = 100

RGBAColor = tuple[int, int, int, int]
RGBColor = tuple[int, int, int]


def load_archivo(size: int, *, weight: int) -> ImageFont.FreeTypeFont:
    """
    Return the Archivo variable font at *size* px and the given *weight* (100-900).
    """
    font = ImageFont.truetype(str(ARCHIVO_PATH), size)
    font.set_variation_by_axes([weight, _ARCHIVO_NORMAL_WIDTH])
    return font


def load_space_mono(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Return the Space Mono font at *size* px, bold or regular.
    """
    path = SPACE_MONO_BOLD_PATH if bold else SPACE_MONO_REGULAR_PATH
    return ImageFont.truetype(str(path), size)


def draw_tracked_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: RGBColor | RGBAColor,
    tracking: float = 0.0,
    anchor: str = "la",
) -> float:
    """
    Draw *text* one glyph at a time, advancing by glyph width plus *tracking*.

    Pillow's ImageDraw.text has no letter-spacing parameter, so tracked labels
    (positive tracking on the mono labels, negative on tight titles) are drawn
    glyph by glyph. Returns the x coordinate just past the last glyph.
    """
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=font, fill=fill, anchor=anchor)
        x += draw.textlength(char, font=font) + tracking
    return x


def draw_filmcase_wordmark(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    *,
    font: ImageFont.FreeTypeFont,
    film_color: RGBColor | RGBAColor,
    case_color: RGBColor | RGBAColor,
    tracking: float = 0.0,
    anchor: str = "la",
) -> float:
    """
    Draw the inline "filmcase" wordmark (``film`` then ``case``) back to back.

    Used for the "IMPORT RECIPE WITH filmcase" label. ``film`` and ``case`` are
    drawn as separate runs so each can take its own colour. Returns the x
    coordinate just past the wordmark.
    """
    x = draw_tracked_text(draw, xy, "film", font=font, fill=film_color, tracking=tracking, anchor=anchor)
    return draw_tracked_text(draw, (x, xy[1]), "case", font=font, fill=case_color, tracking=tracking, anchor=anchor)


def rounded_mask(size: tuple[int, int], radius: int) -> PILImage.Image:
    """
    Return an "L" mode alpha mask: opaque inside a rounded rectangle, else clear.
    """
    mask = PILImage.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size[0] - 1, size[1] - 1)], radius=radius, fill=255
    )
    return mask


def round_corners(img: PILImage.Image, radius: int) -> PILImage.Image:
    """
    Return an RGBA copy of *img* with its corners clipped to *radius*.
    """
    rgba = img.convert("RGBA")
    rgba.putalpha(rounded_mask(rgba.size, radius))
    return rgba


def paste_rounded(
    canvas: PILImage.Image,
    img: PILImage.Image,
    position: tuple[int, int],
    radius: int,
) -> None:
    """
    Alpha-composite *img* onto *canvas* at *position* with rounded corners.

    *canvas* must be in RGBA mode.
    """
    canvas.alpha_composite(round_corners(img, radius), position)


@attrs.frozen
class RenderedCard:
    """
    The output of a card design: the composed image plus its QR payload.

    ``embed_exif`` is True when the recipe JSON should additionally be written
    to the JPEG EXIF UserComment. This is done for no-photo (gradient) cards so
    they remain re-importable even where a scannable QR is not relied upon.
    """

    canvas: PILImage.Image
    json_str: str
    embed_exif: bool


def cover_fill(img: PILImage.Image, target_w: int, target_h: int) -> PILImage.Image:
    """
    Scale *img* so it fills (target_w x target_h) with no empty space, then center-crop.
    """
    scale = max(target_w / img.width, target_h / img.height)
    new_w = int(img.width * scale)
    new_h = int(img.height * scale)
    img = img.resize((new_w, new_h), PILImage.Resampling.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return img.crop((left, top, left + target_w, top + target_h))


def build_gradient(width: int, height: int) -> PILImage.Image:
    """
    Return a soft vertical gradient from GRADIENT_TOP to GRADIENT_BOTTOM.
    """
    img = PILImage.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    r0, g0, b0 = GRADIENT_TOP
    r1, g1, b1 = GRADIENT_BOTTOM
    for y in range(height):
        t = y / (height - 1)
        r = int(r0 + (r1 - r0) * t)
        g = int(g0 + (g1 - g0) * t)
        b = int(b0 + (b1 - b0) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Return a sans-serif TrueType font at *size*, falling back to the PIL default.
    """
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def make_qr(json_str: str, *, size: int = QR_SIZE) -> PILImage.Image:
    """
    Return a *size* x *size* QR code image encoding *json_str*.
    """
    qr_img = qrcode.make(json_str)
    resized: PILImage.Image = qr_img.resize((size, size), PILImage.Resampling.LANCZOS)
    return resized


def embed_recipe_exif(*, filepath: Path, json_str: str) -> None:
    """
    Embed recipe JSON into the UserComment EXIF field of the saved JPEG at filepath.
    """
    exif_bytes = piexif.dump({
        "Exif": {
            piexif.ExifIFD.UserComment: _EXIF_ASCII_PREFIX + json_str.encode("ascii"),
        }
    })
    piexif.insert(exif_bytes, str(filepath))
