"""
Resolves the configured PTP device class from settings and returns fresh instances.

settings.PTP_DEVICE may be a dotted import path (str) or a callable directly.

Also answers which machine the camera is plugged into.  That is a separate
question from which device class to use: PTP_DEVICE picks the server-side
implementation, while CAMERA_TRANSPORT decides whether the server drives the
camera at all.
"""
from __future__ import annotations

import importlib
from typing import cast

from django.conf import settings as django_settings

from src.domain.camera import ptp_device

# Accepted values of settings.CAMERA_TRANSPORT.
TRANSPORT_SERVER = "server"
TRANSPORT_BROWSER = "browser"


def is_browser_transport() -> bool:
    """
    Return whether the camera is driven from the user's browser rather than here.

    When this is true the server has no route to the camera, so the views that
    open a USB connection should decline rather than try.
    """
    return bool(django_settings.CAMERA_TRANSPORT == TRANSPORT_BROWSER)


def get_device() -> ptp_device.PTPDevice:
    """
    Return a fresh, unconnected PTP device as configured in settings.PTP_DEVICE.
    """
    factory = django_settings.PTP_DEVICE
    if isinstance(factory, str):
        module_path, cls_name = factory.rsplit(".", 1)
        factory = getattr(importlib.import_module(module_path), cls_name)
    assert callable(factory)
    return cast(ptp_device.PTPDevice, factory())
