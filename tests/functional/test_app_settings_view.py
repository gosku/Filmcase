from src.domain.settings import queries as settings_queries

URL = "/settings/preferences/"


def _valid_payload(**overrides: str) -> dict[str, str]:
    payload = {
        "camera_transport": "browser",
        "camera_verify_writes": "on",
        "camera_post_read_delay_s": "0.05",
        "camera_pre_write_delay_s": "0.05",
        "camera_post_write_delay_s": "0.05",
        "camera_post_cursor_delay_s": "0.05",
        "camera_inter_slot_delay_s": "0.05",
        "camera_max_retries": "3",
        "camera_retry_backoff_s": "0.15",
        "camera_usb_timeout_ms": "1500",
        "recipe_explorer_page_size": "24",
        "recipe_graph_max_distance": "7",
        "recipe_card_aperture_scrim_top_opacity": "20",
        "recipe_card_aperture_scrim_bottom_opacity": "60",
        "gallery_page_size": "24",
        "image_max_rating": "5",
        "thumbnail_widths": "600,1200",
        "library_prune_guard_fraction": "1.0",
        "library_prune_guard_min_images": "9999999",
        "sync_image_batch_size": "100",
    }
    payload.update(overrides)
    return payload


class TestPreferencesPage:
    def test_get_renders_the_page_grouped_by_app_section(self, client) -> None:
        response = client.get(URL)

        assert response.status_code == 200
        body = response.content.decode()
        for section in ("Camera", "Recipes", "Images", "Library"):
            assert section in body
        # The Preferences tab is highlighted in the settings sidebar.
        assert "settings-nav__item--active" in body

    def test_get_shows_a_description_next_to_a_field(self, client) -> None:
        body = client.get(URL).content.decode()

        # The help text comes from CONSTANCE_CONFIG; the thumbnail warning is a
        # good marker that per-field descriptions render.
        assert "does not regenerate or clear" in body


class TestSavingPreferences:
    def test_post_persists_the_new_values(self, client) -> None:
        response = client.post(URL, data=_valid_payload(image_max_rating="3", gallery_page_size="48"))

        assert response.status_code == 200
        assert "Preferences saved." in response.content.decode()
        assert settings_queries.get_image_max_rating() == 3
        assert settings_queries.get_gallery_page_size() == 48

    def test_post_round_trips_thumbnail_widths(self, client) -> None:
        client.post(URL, data=_valid_payload(thumbnail_widths="600, 1200, 2400"))

        assert settings_queries.get_thumbnail_widths() == (600, 1200, 2400)

    def test_invalid_value_is_rejected_and_not_saved(self, client) -> None:
        response = client.post(URL, data=_valid_payload(image_max_rating="0"))

        assert response.status_code == 200
        assert "Preferences saved." not in response.content.decode()
        # Unchanged from the default the test suite runs on.
        assert settings_queries.get_image_max_rating() == 5

    def test_invalid_thumbnail_widths_are_rejected(self, client) -> None:
        response = client.post(URL, data=_valid_payload(thumbnail_widths="abc"))

        assert response.status_code == 200
        assert "whole numbers" in response.content.decode()
