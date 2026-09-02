import pytest

from src.application.usecases.settings.get_app_settings import get_app_settings
from src.application.usecases.settings.update_app_settings import update_app_settings
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
    library_ignored_directory_prefixes=(".", "@"),
)


@pytest.mark.django_db
class TestSettingsUseCases:
    def test_update_then_get_returns_the_saved_settings(self) -> None:
        update_app_settings(values=SAMPLE)

        assert get_app_settings() == SAMPLE
