from src.domain.recipes import sensors as recipe_sensors


class TestComputeSensorSignature:
    def test_empty_iterable_returns_empty_string(self):
        assert recipe_sensors.compute_sensor_signature(()) == ""

    def test_single_name_lowercases(self):
        assert recipe_sensors.compute_sensor_signature(("X-Trans IV",)) == "x-trans iv"

    def test_multiple_names_are_sorted_and_comma_joined(self):
        assert (
            recipe_sensors.compute_sensor_signature(("X-Trans IV", "GFX"))
            == "gfx,x-trans iv"
        )

    def test_signature_is_order_independent(self):
        a = recipe_sensors.compute_sensor_signature(("X-Trans IV", "GFX"))
        b = recipe_sensors.compute_sensor_signature(("GFX", "X-Trans IV"))

        assert a == b

    def test_signature_is_case_insensitive(self):
        a = recipe_sensors.compute_sensor_signature(("x-TRANS iv",))
        b = recipe_sensors.compute_sensor_signature(("X-Trans IV",))

        assert a == b

    def test_duplicates_collapse(self):
        signature = recipe_sensors.compute_sensor_signature(
            ("X-Trans IV", "X-Trans IV", "GFX")
        )

        assert signature == "gfx,x-trans iv"
