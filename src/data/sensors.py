"""
Canonical Fujifilm sensor names.

Single source of truth for the values stored in the ``Sensor`` table. The
migration seeds ``Sensor`` rows from this tuple; the recipe-data attrs
validator rejects names outside it; the recipe form derives its choices
from it. Keep these three in lock-step by editing this list when a new
sensor is introduced and writing a migration to seed/remove rows.
"""

SENSOR_NAMES: tuple[str, ...] = (
    "X-Trans I",
    "X-Trans II",
    "X-Trans III",
    "X-Trans IV",
    "X-Trans V",
    "GFX",
    "Bayer",
    "EXR-CMOS",
    "Full Spectrum",
)
