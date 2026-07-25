from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image as PILImage

from src.domain.recipes.cards import rendering
from src.domain.recipes.cards.designs import classic


def _quiet_queries() -> tuple[object, object]:
    return (
        patch.object(classic.card_queries, "get_recipe_cover_lines", return_value=()),
        patch.object(classic.card_queries, "get_recipe_as_json", return_value='{"v":2}'),
    )


def _render(design: classic.ClassicDesign, recipe: MagicMock) -> rendering.RenderedCard:
    lines_patch, json_patch = _quiet_queries()
    with (
        patch.object(classic, "_LOGO_PATH", Path("/nonexistent/no_logo.png")),
        lines_patch,
        json_patch,
    ):
        return design.render(recipe=recipe, background_photo_path=None)


class TestClassicDesignMetadata:
    def test_template_name_maps_the_four_legacy_combinations(self) -> None:
        assert classic.ClassicDesign(label_style="long", background_effect="blur").template_name == "long_label"
        assert classic.ClassicDesign(label_style="short", background_effect="blur").template_name == "short_label"
        assert classic.ClassicDesign(label_style="long", background_effect="none").template_name == "long_label_sharp"
        assert classic.ClassicDesign(label_style="short", background_effect="none").template_name == "short_label_sharp"

    def test_output_size_is_square_1080(self) -> None:
        assert classic.ClassicDesign().output_size == (1080, 1080)

    def test_does_not_require_a_background_image(self) -> None:
        assert classic.ClassicDesign().requires_background_image is False


class TestClassicDesignRender:
    def test_canvas_matches_output_size(self) -> None:
        recipe = MagicMock()
        recipe.name = ""

        rendered = _render(classic.ClassicDesign(), recipe)

        assert rendered.canvas.size == (1080, 1080)

    def test_embeds_exif_for_gradient_card(self) -> None:
        recipe = MagicMock()
        recipe.name = ""

        rendered = _render(classic.ClassicDesign(), recipe)

        assert rendered.embed_exif is True

    def test_title_is_rendered_when_recipe_has_a_name(self) -> None:
        recipe = MagicMock()
        recipe.name = "My Recipe"

        rendered = _render(classic.ClassicDesign(), recipe)

        assert self._max_brightness(rendered.canvas, classic._TEXT_PADDING) > 200

    def test_title_is_absent_when_recipe_is_unnamed(self) -> None:
        recipe = MagicMock()
        recipe.name = ""

        rendered = _render(classic.ClassicDesign(), recipe)

        assert self._max_brightness(rendered.canvas, classic._TEXT_PADDING) < 100

    def test_info_side_left_renders_title_in_the_left_half(self) -> None:
        recipe = MagicMock()
        recipe.name = "My Recipe"

        rendered = _render(classic.ClassicDesign(info_side="left"), recipe)

        left_x = classic._TEXT_PADDING
        right_x = 1080 // 2 + classic._TEXT_PADDING
        assert self._max_brightness(rendered.canvas, left_x) > 200
        assert self._max_brightness(rendered.canvas, right_x) < 100

    def test_info_side_right_renders_title_in_the_right_half(self) -> None:
        recipe = MagicMock()
        recipe.name = "My Recipe"

        rendered = _render(classic.ClassicDesign(info_side="right"), recipe)

        left_x = classic._TEXT_PADDING
        right_x = 1080 // 2 + classic._TEXT_PADDING
        assert self._max_brightness(rendered.canvas, right_x) > 200
        assert self._max_brightness(rendered.canvas, left_x) < 100

    def test_missing_logo_file_does_not_raise(self) -> None:
        recipe = MagicMock()
        recipe.name = ""

        # _render already patches _LOGO_PATH to a missing file; reaching here
        # without an exception is the assertion.
        rendered = _render(classic.ClassicDesign(), recipe)

        assert rendered.canvas.size == (1080, 1080)

    def _max_brightness(self, canvas: PILImage.Image, x0: int) -> int:
        p = classic._TEXT_PADDING
        region = canvas.crop((x0, p, x0 + 300, p + classic._TITLE_LINE_HEIGHT))
        return region.getextrema()[0][1]  # max R value in the region
