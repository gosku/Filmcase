"""
Integration tests for the get_camera_model_and_slots use case.

Uses FakePTPDevice via settings.PTP_DEVICE (see conftest autouse fixture).
"""
from src.application.usecases.camera.get_camera_slots import get_camera_model_and_slots
from tests.fakes import FakePTPDevice


class TestGetCameraModelAndSlots:
    def test_returns_the_camera_model_name(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T5")

        camera_name, _ = get_camera_model_and_slots()

        assert camera_name == "X-T5"

    def test_returns_one_state_per_slot_for_the_model(self, settings):
        # X-T5 is a 7-slot camera in the slot-count table.
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="X-T5")

        _, states = get_camera_model_and_slots()

        assert [s.index for s in states] == [1, 2, 3, 4, 5, 6, 7]

    def test_returns_no_slots_for_a_camera_without_custom_slots(self, settings):
        settings.PTP_DEVICE = lambda: FakePTPDevice(camera_name="UNKNOWN_CAM")

        camera_name, states = get_camera_model_and_slots()

        assert camera_name == "UNKNOWN_CAM"
        assert states == []
