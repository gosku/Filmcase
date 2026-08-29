from unittest.mock import MagicMock, patch

from src.domain.settings import events, operations
from src.domain.settings.dataclasses import AppSettings

SAMPLE = AppSettings(
    camera_transport="browser",
    camera_verify_writes=True,
    camera_post_read_delay_s=0.11,
    camera_pre_write_delay_s=0.12,
    camera_post_write_delay_s=0.13,
    camera_post_cursor_delay_s=0.14,
    camera_inter_slot_delay_s=0.15,
    camera_max_retries=4,
    camera_retry_backoff_s=0.16,
    camera_usb_timeout_ms=2000,
    recipe_explorer_page_size=30,
    recipe_graph_max_distance=8,
    recipe_card_aperture_scrim_top_opacity=25,
    recipe_card_aperture_scrim_bottom_opacity=65,
    gallery_page_size=36,
    image_max_rating=7,
    thumbnail_widths=(600, 1200),
    library_prune_guard_fraction=0.5,
    library_prune_guard_min_images=20,
    sync_image_batch_size=50,
)


class TestSerializeWidths:
    def test_joins_widths_with_commas(self) -> None:
        assert operations._serialize_widths((600, 1200)) == "600,1200"

    def test_renders_a_single_width(self) -> None:
        assert operations._serialize_widths((600,)) == "600"


class TestUpdateAppSettings:
    def test_writes_each_value_to_the_store(self) -> None:
        fake_config = MagicMock()
        with patch("src.domain.settings.operations.config", fake_config):
            operations.update_app_settings(values=SAMPLE)

        assert fake_config.CAMERA_TRANSPORT == "browser"
        assert fake_config.IMAGE_MAX_RATING == 7
        assert fake_config.CAMERA_MAX_RETRIES == 4
        # The tuple is serialized to the comma-separated string constance stores.
        assert fake_config.THUMBNAIL_WIDTHS == "600,1200"

    def test_publishes_an_event_describing_the_saved_settings(self, captured_logs) -> None:
        with patch("src.domain.settings.operations.config", MagicMock()):
            operations.update_app_settings(values=SAMPLE)

        updated = [e for e in captured_logs if e.get("event_type") == events.APP_SETTINGS_UPDATED]
        assert len(updated) == 1
        assert updated[0]["image_max_rating"] == 7
        assert updated[0]["camera_transport"] == "browser"
        # thumbnail_widths is logged as the serialized string, not the tuple.
        assert updated[0]["thumbnail_widths"] == "600,1200"
