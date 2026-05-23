import pytest

from src.domain.images import events
from src.domain.recipes.operations import UnknownSensorError, set_recipe_sensors
from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestSetRecipeSensors:
    def test_attaches_named_sensors_and_writes_canonical_signature(self):
        recipe = FujifilmRecipeFactory()

        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans IV", "GFX"))

        recipe.refresh_from_db()
        assert sorted(s.name for s in recipe.sensors.all()) == ["GFX", "X-Trans IV"]
        # Signature is the lowercased, sorted, comma-joined form.
        assert recipe.sensor_signature == "gfx,x-trans iv"

    def test_replaces_existing_sensor_set(self):
        recipe = FujifilmRecipeFactory()
        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans IV",))

        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans V",))

        recipe.refresh_from_db()
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans V"]
        assert recipe.sensor_signature == "x-trans v"

    def test_empty_iterable_clears_sensors_and_signature(self):
        recipe = FujifilmRecipeFactory()
        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans IV",))

        set_recipe_sensors(recipe=recipe, sensor_names=())

        recipe.refresh_from_db()
        assert list(recipe.sensors.all()) == []
        assert recipe.sensor_signature == ""

    def test_order_independent(self):
        a = FujifilmRecipeFactory()
        b = FujifilmRecipeFactory()

        set_recipe_sensors(recipe=a, sensor_names=("X-Trans IV", "GFX"))
        set_recipe_sensors(recipe=b, sensor_names=("GFX", "X-Trans IV"))

        a.refresh_from_db()
        b.refresh_from_db()
        assert a.sensor_signature == b.sensor_signature

    def test_unknown_sensor_name_raises_and_leaves_recipe_unchanged(self):
        recipe = FujifilmRecipeFactory()
        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans IV",))

        with pytest.raises(UnknownSensorError) as exc:
            set_recipe_sensors(
                recipe=recipe, sensor_names=("X-Trans IV", "Definitely Not A Sensor")
            )

        assert exc.value.name == "Definitely Not A Sensor"
        recipe.refresh_from_db()
        # The pre-existing sensor set was not touched.
        assert [s.name for s in recipe.sensors.all()] == ["X-Trans IV"]
        assert recipe.sensor_signature == "x-trans iv"


@pytest.mark.django_db
class TestSetRecipeSensorsEventPublishing:
    def test_publishes_recipe_sensors_set_event(self, captured_logs):
        recipe = FujifilmRecipeFactory()

        set_recipe_sensors(recipe=recipe, sensor_names=("X-Trans IV", "GFX"))

        sensors_set_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_SENSORS_SET
        ]
        assert len(sensors_set_events) == 1
        assert sensors_set_events[0]["recipe_id"] == recipe.pk
        assert sensors_set_events[0]["sensor_signature"] == "gfx,x-trans iv"

    def test_does_not_publish_event_when_validation_fails(self, captured_logs):
        recipe = FujifilmRecipeFactory()

        with pytest.raises(UnknownSensorError):
            set_recipe_sensors(recipe=recipe, sensor_names=("Definitely Not A Sensor",))

        sensors_set_events = [
            e for e in captured_logs if e.get("event_type") == events.RECIPE_SENSORS_SET
        ]
        assert sensors_set_events == []
