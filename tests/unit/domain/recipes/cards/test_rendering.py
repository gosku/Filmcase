from pathlib import Path

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont

from src.domain.recipes.cards import queries as card_queries
from src.domain.recipes.cards import rendering


class TestCoverFill:
    def test_returns_image_at_exact_target_size(self) -> None:
        source = PILImage.new("RGB", (400, 200), (10, 20, 30))

        result = rendering.cover_fill(source, 100, 100)

        assert result.size == (100, 100)

    def test_fills_without_letterboxing_a_wide_source(self) -> None:
        # A wide source cropped to a square must cover the whole target: every
        # pixel comes from the source colour, never an empty/black border.
        source = PILImage.new("RGB", (400, 200), (10, 20, 30))

        result = rendering.cover_fill(source, 100, 100)

        assert result.getextrema() == ((10, 10), (20, 20), (30, 30))


class TestBuildGradient:
    def test_returns_image_at_requested_size(self) -> None:
        gradient = rendering.build_gradient(64, 128)

        assert gradient.size == (64, 128)

    def test_top_row_matches_gradient_top_colour(self) -> None:
        gradient = rendering.build_gradient(64, 128)

        assert gradient.getpixel((0, 0)) == rendering.GRADIENT_TOP


class TestMakeQr:
    def test_returns_qr_at_the_shared_global_size(self) -> None:
        qr = rendering.make_qr('{"v":2}')

        assert qr.size == (rendering.QR_SIZE, rendering.QR_SIZE)


class TestEmbedRecipeExif:
    def test_embedded_json_round_trips_through_the_reader(self, tmp_path: Path) -> None:
        filepath = tmp_path / "card.jpg"
        PILImage.new("RGB", (10, 10), (0, 0, 0)).save(str(filepath), format="JPEG")
        json_str = '{"v":2,"film_simulation":"Provia"}'

        rendering.embed_recipe_exif(filepath=filepath, json_str=json_str)

        assert card_queries._read_exif_recipe(image_path=str(filepath)) == json_str


class TestFontLoaders:
    def test_archivo_loads_as_a_truetype_font(self) -> None:
        font = rendering.load_archivo(52, weight=800)

        assert isinstance(font, ImageFont.FreeTypeFont)

    def test_archivo_weight_changes_glyph_width(self) -> None:
        # A heavier weight renders wider glyphs, so the same text is wider.
        thin = rendering.load_archivo(52, weight=100)
        black = rendering.load_archivo(52, weight=900)
        draw = ImageDraw.Draw(PILImage.new("RGB", (10, 10)))

        assert draw.textlength("filmcase", font=black) > draw.textlength("filmcase", font=thin)

    def test_space_mono_bold_and_regular_both_load(self) -> None:
        assert isinstance(rendering.load_space_mono(24), ImageFont.FreeTypeFont)
        assert isinstance(rendering.load_space_mono(24, bold=True), ImageFont.FreeTypeFont)


class TestDrawTrackedText:
    def test_positive_tracking_widens_the_run(self) -> None:
        font = rendering.load_space_mono(24)
        draw = ImageDraw.Draw(PILImage.new("RGB", (400, 60)))

        untracked_end = rendering.draw_tracked_text(
            draw, (0, 0), "ABCDE", font=font, fill=(255, 255, 255), tracking=0,
        )
        tracked_end = rendering.draw_tracked_text(
            draw, (0, 0), "ABCDE", font=font, fill=(255, 255, 255), tracking=5,
        )

        assert tracked_end > untracked_end


class TestFilmcaseWordmark:
    def test_advances_past_the_start(self) -> None:
        font = rendering.load_archivo(27, weight=900)
        draw = ImageDraw.Draw(PILImage.new("RGB", (400, 60)))

        end = rendering.draw_filmcase_wordmark(
            draw, (10, 0), font=font, film_color=(239, 68, 68), case_color=(17, 24, 39),
        )

        assert end > 10


class TestRoundedCorners:
    def test_rounded_mask_clears_corners_and_fills_centre(self) -> None:
        mask = rendering.rounded_mask((100, 100), radius=30)

        assert mask.getpixel((0, 0)) == 0
        assert mask.getpixel((50, 50)) == 255

    def test_round_corners_makes_corner_transparent(self) -> None:
        img = PILImage.new("RGB", (100, 100), (10, 20, 30))

        rounded = rendering.round_corners(img, radius=30)

        assert rounded.mode == "RGBA"
        assert rounded.getpixel((0, 0))[3] == 0
        assert rounded.getpixel((50, 50))[3] == 255

    def test_paste_rounded_composites_onto_canvas(self) -> None:
        canvas = PILImage.new("RGBA", (200, 200), (0, 0, 0, 255))
        patch = PILImage.new("RGB", (100, 100), (255, 0, 0))

        rendering.paste_rounded(canvas, patch, (50, 50), radius=20)

        # Centre of the pasted patch is red; a canvas corner is untouched black.
        assert canvas.getpixel((100, 100))[:3] == (255, 0, 0)
        assert canvas.getpixel((0, 0))[:3] == (0, 0, 0)
