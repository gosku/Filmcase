"""
Resolves the configured PTP device class from settings and returns fresh instances.

settings.PTP_DEVICE may be a dotted import path (str) or a callable directly.
"""
from __future__ import annotations

import importlib

from django.conf import settings as django_settings

from src.domain.camera import ptp_device


def get_device() -> ptp_device.PTPDevice:
    """Return a fresh, unconnected PTP device as configured in settings.PTP_DEVICE."""
    factory = django_settings.PTP_DEVICE
    if isinstance(factory, str):
        module_path, cls_name = factory.rsplit(".", 1)
        factory = getattr(importlib.import_module(module_path), cls_name)
    return factory()
