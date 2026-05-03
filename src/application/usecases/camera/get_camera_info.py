import attrs

from src.domain.camera import device_config
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries


@attrs.frozen
class CameraStatusResult:
    info: camera_queries.CameraInfo
    custom_slot_count: int
    slots: tuple[camera_queries.SlotState, ...] | None  # None when not requested


def get_camera_status(*, read_slots: bool) -> CameraStatusResult:
    """
    Connect to the camera, read its identity, and optionally read slot states.

    Manages the full device lifecycle: connect → read → disconnect.

    Raises:
        ptp_device.CameraConnectionError: If the camera is unreachable or a read fails.
    """
    device = device_config.get_device()
    device.connect()
    try:
        info = camera_queries.camera_info(device)
        slot_count = camera_queries.custom_slot_count(info.camera_name)
        slots = None
        if read_slots and slot_count > 0:
            slots = tuple(camera_queries.slot_states(device, slot_count))
        return CameraStatusResult(info=info, custom_slot_count=slot_count, slots=slots)
    finally:
        device.disconnect()
