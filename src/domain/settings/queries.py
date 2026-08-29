"""
Typed read access to the dynamic (database-backed) application settings.

Every runtime-changeable setting is reached through the getters here rather than
through ``django.conf.settings`` or ``constance.config`` directly. constance
returns the saved database value or, when none has been saved, the env-seeded
default declared in ``settings.CONSTANCE_CONFIG``; these getters add the static
type it cannot, and give one place to stub the store in tests.
"""
from __future__ import annotations

from constance import config

from src.domain.settings.dataclasses import AppSettings


def _parse_widths(raw: str) -> tuple[int, ...]:
    """
    Turn the comma-separated ``THUMBNAIL_WIDTHS`` string into a tuple of ints.
    """
    return tuple(int(part) for part in raw.split(",") if part.strip())


def get_camera_transport() -> str:
    value: str = config.CAMERA_TRANSPORT
    return value


def get_camera_verify_writes() -> bool:
    value: bool = config.CAMERA_VERIFY_WRITES
    return value


def get_camera_post_read_delay_s() -> float:
    value: float = config.CAMERA_POST_READ_DELAY_S
    return value


def get_camera_pre_write_delay_s() -> float:
    value: float = config.CAMERA_PRE_WRITE_DELAY_S
    return value


def get_camera_post_write_delay_s() -> float:
    value: float = config.CAMERA_POST_WRITE_DELAY_S
    return value


def get_camera_post_cursor_delay_s() -> float:
    value: float = config.CAMERA_POST_CURSOR_DELAY_S
    return value


def get_camera_inter_slot_delay_s() -> float:
    value: float = config.CAMERA_INTER_SLOT_DELAY_S
    return value


def get_camera_max_retries() -> int:
    value: int = config.CAMERA_MAX_RETRIES
    return value


def get_camera_retry_backoff_s() -> float:
    value: float = config.CAMERA_RETRY_BACKOFF_S
    return value


def get_camera_usb_timeout_ms() -> int:
    value: int = config.CAMERA_USB_TIMEOUT_MS
    return value


def get_recipe_explorer_page_size() -> int:
    value: int = config.RECIPE_EXPLORER_PAGE_SIZE
    return value


def get_recipe_graph_max_distance() -> int:
    value: int = config.RECIPE_GRAPH_MAX_DISTANCE
    return value


def get_recipe_card_aperture_scrim_top_opacity() -> int:
    value: int = config.RECIPE_CARD_APERTURE_SCRIM_TOP_OPACITY
    return value


def get_recipe_card_aperture_scrim_bottom_opacity() -> int:
    value: int = config.RECIPE_CARD_APERTURE_SCRIM_BOTTOM_OPACITY
    return value


def get_gallery_page_size() -> int:
    value: int = config.GALLERY_PAGE_SIZE
    return value


def get_image_max_rating() -> int:
    value: int = config.IMAGE_MAX_RATING
    return value


def get_thumbnail_widths() -> tuple[int, ...]:
    raw: str = config.THUMBNAIL_WIDTHS
    return _parse_widths(raw)


def get_library_prune_guard_fraction() -> float:
    value: float = config.LIBRARY_PRUNE_GUARD_FRACTION
    return value


def get_library_prune_guard_min_images() -> int:
    value: int = config.LIBRARY_PRUNE_GUARD_MIN_IMAGES
    return value


def get_sync_image_batch_size() -> int:
    value: int = config.SYNC_IMAGE_BATCH_SIZE
    return value


def get_app_settings() -> AppSettings:
    """
    Read every dynamic setting into a single typed ``AppSettings`` value.
    """
    return AppSettings(
        camera_transport=get_camera_transport(),
        camera_verify_writes=get_camera_verify_writes(),
        camera_post_read_delay_s=get_camera_post_read_delay_s(),
        camera_pre_write_delay_s=get_camera_pre_write_delay_s(),
        camera_post_write_delay_s=get_camera_post_write_delay_s(),
        camera_post_cursor_delay_s=get_camera_post_cursor_delay_s(),
        camera_inter_slot_delay_s=get_camera_inter_slot_delay_s(),
        camera_max_retries=get_camera_max_retries(),
        camera_retry_backoff_s=get_camera_retry_backoff_s(),
        camera_usb_timeout_ms=get_camera_usb_timeout_ms(),
        recipe_explorer_page_size=get_recipe_explorer_page_size(),
        recipe_graph_max_distance=get_recipe_graph_max_distance(),
        recipe_card_aperture_scrim_top_opacity=get_recipe_card_aperture_scrim_top_opacity(),
        recipe_card_aperture_scrim_bottom_opacity=get_recipe_card_aperture_scrim_bottom_opacity(),
        gallery_page_size=get_gallery_page_size(),
        image_max_rating=get_image_max_rating(),
        thumbnail_widths=get_thumbnail_widths(),
        library_prune_guard_fraction=get_library_prune_guard_fraction(),
        library_prune_guard_min_images=get_library_prune_guard_min_images(),
        sync_image_batch_size=get_sync_image_batch_size(),
    )
