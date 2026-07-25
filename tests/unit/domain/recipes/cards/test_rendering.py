from pathlib import Path

from PIL import Image as PILImage

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
