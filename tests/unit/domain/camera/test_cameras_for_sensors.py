from src.domain.recipes import sensors as recipe_sensors


class TestCamerasForSensors:
    def test_empty_iterable_returns_empty_tuple(self):
        assert recipe_sensors.cameras_for_sensors(()) == ()

    def test_unknown_sensor_returns_empty_tuple(self):
        assert recipe_sensors.cameras_for_sensors(("Imaginary Sensor",)) == ()

    def test_single_sensor_returns_only_matching_cameras(self):
        # All returned cameras must have sensor "X-Trans IV" in the mapping.
        result = recipe_sensors.cameras_for_sensors(("X-Trans IV",))

        # Spot-check a known X-Trans IV camera is present and a known
        # X-Trans V camera is absent.
        assert "X-T4" in result
        assert "X-S10" in result
        assert "X-T5" not in result
        assert "GFX100S" not in result

    def test_multiple_sensors_union_cameras(self):
        result = recipe_sensors.cameras_for_sensors(("X-Trans IV", "GFX"))

        # X-Trans IV body
        assert "X-T4" in result
        # GFX body
        assert "GFX100S" in result

    def test_result_is_sorted(self):
        result = recipe_sensors.cameras_for_sensors(("X-Trans IV", "GFX"))

        assert list(result) == sorted(result)

    def test_duplicates_in_input_do_not_duplicate_cameras(self):
        result = recipe_sensors.cameras_for_sensors(
            ("X-Trans IV", "X-Trans IV")
        )

        assert len(result) == len(set(result))
