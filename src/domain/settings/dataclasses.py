from __future__ import annotations

import attrs


@attrs.frozen
class AppSettings:
    """
    The full set of user-editable application settings, read from or written to
    the dynamic-settings store as one typed unit.

    Field names match the constance keys in ``settings.CONSTANCE_CONFIG`` in
    lower snake case; ``thumbnail_widths`` is held as a tuple here even though
    constance stores it as a comma-separated string.
    """

    camera_transport: str
    camera_verify_writes: bool
    camera_post_read_delay_s: float
    camera_pre_write_delay_s: float
    camera_post_write_delay_s: float
    camera_post_cursor_delay_s: float
    camera_inter_slot_delay_s: float
    camera_max_retries: int
    camera_retry_backoff_s: float
    camera_usb_timeout_ms: int
    recipe_explorer_page_size: int
    recipe_graph_max_distance: int
    recipe_card_aperture_scrim_top_opacity: int
    recipe_card_aperture_scrim_bottom_opacity: int
    gallery_page_size: int
    image_max_rating: int
    thumbnail_widths: tuple[int, ...]
    library_prune_guard_fraction: float
    library_prune_guard_min_images: int
    sync_image_batch_size: int
