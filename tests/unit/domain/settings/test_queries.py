from types import SimpleNamespace
from unittest.mock import patch

from src.domain.settings import queries
from src.domain.settings.dataclasses import AppSettings

# Every constance key set to a distinct value, so a getter reading the wrong key
# is caught. THUMBNAIL_WIDTHS is the comma-separated string constance stores.
_ALL_VALUES = {
    "CAMERA_TRANSPORT": "browser",
    "CAMERA_VERIFY_WRITES": True,
    "CAMERA_POST_READ_DELAY_S": 0.11,
    "CAMERA_PRE_WRITE_DELAY_S": 0.12,
    "CAMERA_POST_WRITE_DELAY_S": 0.13,
    "CAMERA_POST_CURSOR_DELAY_S": 0.14,
    "CAMERA_INTER_SLOT_DELAY_S": 0.15,
    "CAMERA_MAX_RETRIES": 4,
    "CAMERA_RETRY_BACKOFF_S": 0.16,
    "CAMERA_USB_TIMEOUT_MS": 2000,
    "RECIPE_EXPLORER_PAGE_SIZE": 30,
    "RECIPE_GRAPH_MAX_DISTANCE": 8,
    "RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY": 25,
    "RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY": 65,
    "GALLERY_PAGE_SIZE": 36,
    "IMAGE_MAX_RATING": 7,
    "THUMBNAIL_WIDTHS": "600,1200",
    "LIBRARY_PRUNE_GUARD_FRACTION": 0.5,
    "LIBRARY_PRUNE_GUARD_MIN_IMAGES": 20,
    "SYNC_IMAGE_BATCH_SIZE": 50,
}


def _fake_config(**overrides: object) -> SimpleNamespace:
    values = {**_ALL_VALUES, **overrides}
    return SimpleNamespace(**values)


class TestParseWidths:
    def test_parses_a_single_width(self) -> None:
        assert queries._parse_widths("600") == (600,)

    def test_parses_several_widths(self) -> None:
        assert queries._parse_widths("600,1200,2400") == (600, 1200, 2400)

    def test_ignores_blank_entries(self) -> None:
        assert queries._parse_widths("600, ,1200") == (600, 1200)


class TestGetThumbnailWidths:
    def test_returns_the_parsed_tuple(self) -> None:
        with patch("src.domain.settings.queries.config", _fake_config(THUMBNAIL_WIDTHS="600,1200")):
            assert queries.get_thumbnail_widths() == (600, 1200)


class TestGetCameraTransport:
    def test_returns_the_stored_value(self) -> None:
        with patch("src.domain.settings.queries.config", _fake_config(CAMERA_TRANSPORT="browser")):
            assert queries.get_camera_transport() == "browser"


class TestGetAppSettings:
    def test_assembles_every_setting_into_the_dataclass(self) -> None:
        with patch("src.domain.settings.queries.config", _fake_config()):
            result = queries.get_app_settings()

        assert result == AppSettings(
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
