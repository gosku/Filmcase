"""
Write access to the dynamic (database-backed) application settings.

Saving a value here creates a constance database override, after which reads
return the saved value rather than the env-seeded default. With caching disabled
every process sees the new value on its next read, so a change takes effect
without restarting the app.
"""
from __future__ import annotations

from constance import config

from src.domain.settings import events
from src.domain.settings.dataclasses import AppSettings


def _serialize_widths(widths: tuple[int, ...]) -> str:
    """
    Render thumbnail widths as the comma-separated string constance stores.
    """
    return ",".join(str(width) for width in widths)


def update_app_settings(*, values: AppSettings) -> None:
    """
    Persist every dynamic setting to the database-backed store.
    """
    config.CAMERA_TRANSPORT = values.camera_transport
    config.CAMERA_VERIFY_WRITES = values.camera_verify_writes
    config.CAMERA_POST_READ_DELAY_S = values.camera_post_read_delay_s
    config.CAMERA_PRE_WRITE_DELAY_S = values.camera_pre_write_delay_s
    config.CAMERA_POST_WRITE_DELAY_S = values.camera_post_write_delay_s
    config.CAMERA_POST_CURSOR_DELAY_S = values.camera_post_cursor_delay_s
    config.CAMERA_INTER_SLOT_DELAY_S = values.camera_inter_slot_delay_s
    config.CAMERA_MAX_RETRIES = values.camera_max_retries
    config.CAMERA_RETRY_BACKOFF_S = values.camera_retry_backoff_s
    config.CAMERA_USB_TIMEOUT_MS = values.camera_usb_timeout_ms
    config.RECIPE_EXPLORER_PAGE_SIZE = values.recipe_explorer_page_size
    config.RECIPE_GRAPH_MAX_DISTANCE = values.recipe_graph_max_distance
    config.RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY = values.recipe_card_aperture_scrim_top_opacity
    config.RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY = values.recipe_card_aperture_scrim_bottom_opacity
    config.GALLERY_PAGE_SIZE = values.gallery_page_size
    config.IMAGE_MAX_RATING = values.image_max_rating
    config.THUMBNAIL_WIDTHS = _serialize_widths(values.thumbnail_widths)
    config.LIBRARY_PRUNE_GUARD_FRACTION = values.library_prune_guard_fraction
    config.LIBRARY_PRUNE_GUARD_MIN_IMAGES = values.library_prune_guard_min_images
    config.SYNC_IMAGE_BATCH_SIZE = values.sync_image_batch_size

    events.publish_event(
        event_type=events.APP_SETTINGS_UPDATED,
        camera_transport=values.camera_transport,
        camera_verify_writes=values.camera_verify_writes,
        camera_post_read_delay_s=values.camera_post_read_delay_s,
        camera_pre_write_delay_s=values.camera_pre_write_delay_s,
        camera_post_write_delay_s=values.camera_post_write_delay_s,
        camera_post_cursor_delay_s=values.camera_post_cursor_delay_s,
        camera_inter_slot_delay_s=values.camera_inter_slot_delay_s,
        camera_max_retries=values.camera_max_retries,
        camera_retry_backoff_s=values.camera_retry_backoff_s,
        camera_usb_timeout_ms=values.camera_usb_timeout_ms,
        recipe_explorer_page_size=values.recipe_explorer_page_size,
        recipe_graph_max_distance=values.recipe_graph_max_distance,
        recipe_card_aperture_scrim_top_opacity=values.recipe_card_aperture_scrim_top_opacity,
        recipe_card_aperture_scrim_bottom_opacity=values.recipe_card_aperture_scrim_bottom_opacity,
        gallery_page_size=values.gallery_page_size,
        image_max_rating=values.image_max_rating,
        thumbnail_widths=_serialize_widths(values.thumbnail_widths),
        library_prune_guard_fraction=values.library_prune_guard_fraction,
        library_prune_guard_min_images=values.library_prune_guard_min_images,
        sync_image_batch_size=values.sync_image_batch_size,
    )
