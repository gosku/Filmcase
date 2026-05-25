"""Unit tests for the CAMERA_TO_SENSOR mapping itself.

End-to-end coverage of ``exif_to_recipe`` populating sensors from a real
camera_model value lives in
``tests/integration/domain/test_exif_to_recipe.py``.
"""

from src.data import sensors as sensors_module
from src.data.camera import constants as camera_constants


class TestCameraToSensorMappingIntegrity:
    def test_every_mapped_sensor_name_is_in_seeded_set(self):
        # If the mapping references a sensor name that isn't seeded, the
        # FujifilmRecipeData validator would reject the EXIF-produced data
        # and the import would silently fail. Guard against that.
        unknown = {
            sensor
            for sensor in camera_constants.CAMERA_TO_SENSOR.values()
            if sensor not in sensors_module.SENSOR_NAMES
        }

        assert not unknown, f"CAMERA_TO_SENSOR references unknown sensors: {unknown}"

    def test_no_duplicate_camera_keys(self):
        # Python dict literal already enforces this, but the explicit check
        # surfaces a regression cleanly if a future merge conflict drops
        # entries.
        keys = list(camera_constants.CAMERA_TO_SENSOR.keys())
        assert len(keys) == len(set(keys))

    def test_every_seeded_sensor_is_reachable_from_at_least_one_camera(self):
        # "Full Spectrum" describes an IR-converted body (a hardware mod) and
        # cannot be derived from a stock EXIF model -- it's set explicitly by
        # the user or by a catalogue importer. Every OTHER seeded sensor
        # should be reachable from at least one mapped camera model so EXIF
        # imports can populate every generation we ship.
        sensors_via_cameras = set(camera_constants.CAMERA_TO_SENSOR.values())
        expected = set(sensors_module.SENSOR_NAMES) - {"Full Spectrum"}

        missing = expected - sensors_via_cameras
        assert not missing, f"Sensors not reachable from any camera model: {missing}"
