import pytest

from src.data import models
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestFujifilmRecipeSetSensorSignature:
    def test_writes_signature_field(self):
        recipe = FujifilmRecipeFactory()

        recipe.set_sensor_signature(sensor_signature="gfx,x-trans iv")

        recipe.refresh_from_db()
        assert recipe.sensor_signature == "gfx,x-trans iv"

    def test_overwrites_previous_signature(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensor_signature(sensor_signature="x-trans iv")

        recipe.set_sensor_signature(sensor_signature="x-trans v")

        recipe.refresh_from_db()
        assert recipe.sensor_signature == "x-trans v"

    def test_accepts_empty_string(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensor_signature(sensor_signature="x-trans iv")

        recipe.set_sensor_signature(sensor_signature="")

        recipe.refresh_from_db()
        assert recipe.sensor_signature == ""

    def test_caller_supplies_value_verbatim(self):
        # The mutator is dumb: it stores the string exactly as provided rather
        # than deriving it from anything. The canonical-signature contract
        # lives in src.domain.recipes.sensors.compute_sensor_signature.
        recipe = FujifilmRecipeFactory()

        recipe.set_sensor_signature(sensor_signature="anything-the-caller-passes-in")

        recipe.refresh_from_db()
        assert recipe.sensor_signature == "anything-the-caller-passes-in"


@pytest.mark.django_db
class TestFujifilmRecipeSetSensors:
    def test_attaches_provided_sensors(self):
        recipe = FujifilmRecipeFactory()
        x_trans_iv = models.Sensor.objects.get(name="X-Trans IV")
        gfx = models.Sensor.objects.get(name="GFX")

        recipe.set_sensors(sensors=[x_trans_iv, gfx])

        recipe.refresh_from_db()
        assert sorted(s.name for s in recipe.sensors.all()) == ["GFX", "X-Trans IV"]

    def test_accepts_a_queryset(self):
        recipe = FujifilmRecipeFactory()

        recipe.set_sensors(
            sensors=models.Sensor.objects.filter(name__in=["X-Trans IV", "GFX"])
        )

        recipe.refresh_from_db()
        assert sorted(s.name for s in recipe.sensors.all()) == ["GFX", "X-Trans IV"]

    def test_replaces_existing_sensors(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="X-Trans IV"))

        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="X-Trans V"))

        recipe.refresh_from_db()
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans V"]

    def test_empty_iterable_clears_the_set(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="X-Trans IV"))

        recipe.set_sensors(sensors=[])

        recipe.refresh_from_db()
        assert list(recipe.sensors.all()) == []

    def test_does_not_touch_sensor_signature(self):
        # The mutators are independent: writing the M2M leaves the signature
        # field alone. The operation in src.domain.recipes.operations is
        # responsible for keeping them in sync.
        recipe = FujifilmRecipeFactory()
        recipe.set_sensor_signature(sensor_signature="x-trans iv")

        recipe.set_sensors(sensors=models.Sensor.objects.filter(name="GFX"))

        recipe.refresh_from_db()
        assert recipe.sensor_signature == "x-trans iv"
        assert [s.name for s in recipe.sensors.all()] == ["GFX"]
