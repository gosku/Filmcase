from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest
from django.test import override_settings

from src.domain.images.thumbnails.queries import thumbnail_cache_path
from tests.factories import ImageFactory

FIXTURE_IMAGE = Path(__file__).resolve().parent.parent / "fixtures" / "images" / "XS107114.JPG"
THUMBNAIL_WIDTH = 600
GENERATE_URL = "/settings/thumbnails/generate/"
PREFERENCES_URL = "/settings/preferences/"

_WORKER = "src.application.usecases.images.trigger_thumbnail_generation.workertasks.is_celery_worker_available"
_BACKGROUND = "src.application.usecases.images.trigger_thumbnail_generation.background.run_in_background"


def _run_inline(func: Callable[..., object], /, **kwargs: object) -> None:
    func(**kwargs)


@pytest.mark.django_db
class TestSettingsRedirect:
    def test_settings_redirects_to_library(self, client):
        response = client.get("/settings/")

        assert response.status_code == 302
        assert response["Location"] == "/settings/library/"


@pytest.mark.django_db
class TestGenerateThumbnails:
    @override_settings(USE_ASYNC_TASKS=True)
    def test_enqueues_and_redirects_with_the_queued_flag_when_a_worker_is_up(self, client, tmp_path):
        ImageFactory(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with patch(_WORKER, return_value=True), override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            response = client.post(GENERATE_URL)

        assert response.status_code == 302
        assert response["Location"] == f"{PREFERENCES_URL}?thumbnails=queued&enqueued=1&cached=0"

    @override_settings(USE_ASYNC_TASKS=False)
    def test_generates_files_and_redirects_with_the_started_flag_in_sync_mode(self, client, tmp_path):
        ImageFactory(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with patch(_BACKGROUND, side_effect=_run_inline), override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            response = client.post(GENERATE_URL)
            expected = thumbnail_cache_path(original_path=FIXTURE_IMAGE, width=THUMBNAIL_WIDTH)

        assert response.status_code == 302
        assert response["Location"] == f"{PREFERENCES_URL}?thumbnails=started"
        assert expected.is_file()

    @override_settings(USE_ASYNC_TASKS=True)
    def test_redirects_with_the_no_worker_flag_and_generates_nothing(self, client, tmp_path):
        ImageFactory(filename="XS107114.JPG", filepath=str(FIXTURE_IMAGE))

        with patch(_WORKER, return_value=False), override_settings(THUMBNAIL_CACHE_DIR=tmp_path):
            response = client.post(GENERATE_URL)

        assert response.status_code == 302
        assert response["Location"] == f"{PREFERENCES_URL}?thumbnails=no-worker"
        assert not any(tmp_path.iterdir())


@pytest.mark.django_db
class TestPreferencesThumbnailBanner:
    def test_queued_flag_renders_the_count_banner(self, client):
        response = client.get(f"{PREFERENCES_URL}?thumbnails=queued&enqueued=5&cached=2")

        body = response.content.decode()
        assert "Queued 5 thumbnails for generation (2 already cached)." in body
        assert "banner--ok" in body

    def test_started_flag_renders_the_background_banner(self, client):
        response = client.get(f"{PREFERENCES_URL}?thumbnails=started")

        assert "Generating thumbnails in the background." in response.content.decode()

    def test_no_worker_flag_renders_an_error_banner(self, client):
        response = client.get(f"{PREFERENCES_URL}?thumbnails=no-worker")

        body = response.content.decode()
        assert "No image worker is running to generate thumbnails." in body
        assert "banner--error" in body

    def test_no_thumbnail_flag_shows_no_banner(self, client):
        response = client.get(PREFERENCES_URL)

        assert "Generating thumbnails" not in response.content.decode()

    def test_generate_button_is_wired_to_its_own_form_not_the_settings_save(self, client):
        response = client.get(PREFERENCES_URL)

        body = response.content.decode()
        # The button lives inside the settings section but submits a separate
        # form, so generating thumbnails never persists the settings form.
        assert 'form="generate-thumbnails-form"' in body
        assert 'id="generate-thumbnails-form"' in body
        assert 'action="/settings/thumbnails/generate/"' in body
