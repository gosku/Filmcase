import pytest
from django.db import IntegrityError

from src.data import models
from src.data import sensors as sensors_module


@pytest.mark.django_db
class TestSensorModel:
    def test_seeded_sensor_names_match_constant(self):
        # The migration seeds the table from a literal inlined list; this
        # asserts that list matches the canonical SENSOR_NAMES constant the
        # rest of the codebase reads. If the two ever drift, this test fails
        # and points to the migration that needs an update.
        seeded = set(models.Sensor.objects.values_list("name", flat=True))
        assert seeded == set(sensors_module.SENSOR_NAMES)

    def test_sensor_name_is_unique(self):
        # The unique_sensor_name constraint must reject a duplicate name.
        with pytest.raises(IntegrityError):
            models.Sensor.objects.create(name="X-Trans IV")

    def test_str_includes_id_and_name(self):
        sensor = models.Sensor.objects.get(name="X-Trans V")

        assert str(sensor) == f"#{sensor.id} X-Trans V"
