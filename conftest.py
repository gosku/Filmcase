from unittest import mock

import django.conf
import pytest
import structlog

from tests.fakes import FakePTPDevice


def pytest_configure(config):
    settings = django.conf.settings
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    # Zero out all camera I/O delays so tests run at full speed. The dynamic
    # settings are read through the constance-backed config, which the autouse
    # _dynamic_settings fixture below proxies onto these Django settings.
    settings.CAMERA_POST_READ_DELAY_S   = 0
    settings.CAMERA_PRE_WRITE_DELAY_S   = 0
    settings.CAMERA_POST_WRITE_DELAY_S  = 0
    settings.CAMERA_POST_CURSOR_DELAY_S = 0
    settings.CAMERA_INTER_SLOT_DELAY_S  = 0
    settings.CAMERA_RETRY_BACKOFF_S     = 0
    config.addinivalue_line(
        "markers",
        "real_constance: run against the real constance database backend instead "
        "of the settings-backed proxy (needs django_db).",
    )


class _SettingsBackedConfig:
    """
    Stand-in for ``constance.config`` used in tests.

    Reads fall through to ``django.conf.settings`` so the existing ``settings``
    fixture keeps driving behaviour and no database is touched; writes are kept
    in a per-instance override dict, so saving settings in a test neither leaks
    across tests nor needs a migration. ``THUMBNAIL_WIDTHS`` is exposed as the
    comma-separated string constance stores, converting from the settings tuple.
    """

    def __init__(self) -> None:
        object.__setattr__(self, "_overrides", {})

    def __getattr__(self, name):
        overrides = object.__getattribute__(self, "_overrides")
        if name in overrides:
            return overrides[name]
        value = getattr(django.conf.settings, name)
        if name == "THUMBNAIL_WIDTHS" and isinstance(value, tuple):
            return ",".join(str(width) for width in value)
        return value

    def __setattr__(self, name, value):
        object.__getattribute__(self, "_overrides")[name] = value


@pytest.fixture(autouse=True)
def _dynamic_settings(request):
    """
    Route constance reads/writes through the settings-backed proxy by default.

    Tests marked ``real_constance`` opt out and use the real database backend.
    """
    if request.node.get_closest_marker("real_constance"):
        yield
        return
    fake = _SettingsBackedConfig()
    with (
        mock.patch("src.domain.settings.queries.config", fake),
        mock.patch("src.domain.settings.operations.config", fake),
    ):
        yield


@pytest.fixture(autouse=True)
def _default_ptp_device(settings):
    """Point PTP_DEVICE at FakePTPDevice for every test."""
    settings.PTP_DEVICE = FakePTPDevice


@pytest.fixture()
def captured_logs():
    """Capture structlog events emitted during a test."""
    output = []

    def capture_processor(logger, method_name, event_dict):
        output.append(event_dict.copy())
        raise structlog.DropEvent

    old_config = structlog.get_config()
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            capture_processor,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
    yield output
    structlog.configure(**old_config)
