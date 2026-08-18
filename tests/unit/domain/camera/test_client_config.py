"""
Unit tests for the queries that describe the camera to a client.

The browser runs a port of the same push sequence, so these queries are the
contract between the two implementations: whatever they leave out, the client
cannot know.
"""

from __future__ import annotations

import attrs
import django.conf
import pytest

from src.domain.camera import queries as camera_queries


def _camera_setting_names() -> set[str]:
    return {name for name in dir(django.conf.settings) if name.startswith("CAMERA_")}


class TestClientCameraSettings:
    def test_covers_every_camera_setting(self) -> None:
        # The point of the query is that both transports run on one
        # configuration.  A new CAMERA_* setting that nobody shared with the
        # client would silently give the browser different timings from the
        # server, so adding one has to be a decision rather than an oversight.
        fields = {field.name for field in attrs.fields(camera_queries.ClientCameraSettings)}

        assert fields == _camera_setting_names()

    def test_reads_the_current_setting_values(self, settings) -> None:
        settings.CAMERA_TRANSPORT = "browser"
        settings.CAMERA_MAX_RETRIES = 7
        settings.CAMERA_RETRY_BACKOFF_S = 0.25

        result = camera_queries.client_camera_settings()

        assert result.CAMERA_TRANSPORT == "browser"
        assert result.CAMERA_MAX_RETRIES == 7
        assert result.CAMERA_RETRY_BACKOFF_S == 0.25

    def test_reads_settings_at_call_time_not_import_time(self, settings) -> None:
        settings.CAMERA_PRE_WRITE_DELAY_S = 0.1
        before = camera_queries.client_camera_settings()

        settings.CAMERA_PRE_WRITE_DELAY_S = 0.2
        after = camera_queries.client_camera_settings()

        assert before.CAMERA_PRE_WRITE_DELAY_S == 0.1
        assert after.CAMERA_PRE_WRITE_DELAY_S == 0.2

    def test_is_immutable(self) -> None:
        result = camera_queries.client_camera_settings()

        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            result.CAMERA_MAX_RETRIES = 99  # type: ignore[misc]
