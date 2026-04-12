from unittest.mock import MagicMock, patch

import pytest

from src.domain.images import events
from src.domain.images.dataclasses import ImageExifData
from src.domain.recipes.operations import get_or_create_recipe_from_metadata

# ImageExifData with valid values for all fields consumed by exif_to_recipe.
METADATA = ImageExifData(
    film_simulation="Classic Negative",
    color="+4 (highest)",
    d_range_priority="Fixed",
    d_range_priority_auto="Strong",
    white_balance="Auto",
    white_balance_fine_tune="Red +3, Blue -5",
    color_temperature="",
    grain_effect_roughness="Off",
    grain_effect_size="Off",
    color_chrome_effect="Off",
    color_chrome_fx_blue="Strong",
    sharpness="-1 (medium soft)",
    noise_reduction="-4 (weakest)",
    clarity="0",
    dynamic_range_setting="Manual",
    development_dynamic_range="400",
    highlight_tone="0 (normal)",
    shadow_tone="+1 (medium hard)",
    bw_adjustment="0",
    bw_magenta_green="0",
)


class TestGetOrCreateRecipeFromMetadataEventPublishing:
    def test_publishes_event_when_recipe_is_created(self, captured_logs):
        recipe = MagicMock()
        recipe.pk = 99
        recipe.film_simulation = "Classic Negative"

        with patch("src.data.models.FujifilmRecipe.get_or_create", return_value=(recipe, True)):
            get_or_create_recipe_from_metadata(metadata=METADATA)

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert len(created_events) == 1
        assert created_events[0]["recipe_id"] == 99
        assert created_events[0]["film_simulation"] == "Classic Negative"

    def test_does_not_publish_event_when_recipe_already_exists(self, captured_logs):
        recipe = MagicMock()

        with patch("src.data.models.FujifilmRecipe.get_or_create", return_value=(recipe, False)):
            get_or_create_recipe_from_metadata(metadata=METADATA)

        created_events = [e for e in captured_logs if e.get("event_type") == events.RECIPE_CREATED]
        assert created_events == []
