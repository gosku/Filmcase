"""
The served camera profile, and the guard that the committed JS fixture matches it.

The browser runs its backup codec on the X-T2 layout served here, asserted
against the same blob fixture as the Python codec. The committed
xt2_profile.json is that served payload; if this fails, regenerate it with
tests/fixtures/camera/generate_xt2_profile.py.
"""
import json
from pathlib import Path

from src.domain.camera import queries as camera_queries

_FIXTURE = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "camera" / "xt2_profile.json"


class TestClientCameraProfile:
    def test_maps_the_x_t2_to_the_backup_blob_interface(self) -> None:
        profile = camera_queries.client_camera_profile()

        assert profile["interface_by_model"]["X-T2"] == "backup_blob"
        assert profile["default_interface"] == "per_property"

    def test_xt2_layout_has_the_blob_geometry(self) -> None:
        xt2 = camera_queries.client_camera_profile()["xt2"]

        assert xt2["blob_size"] == 5660
        assert xt2["slot_count"] == 7
        assert xt2["off"]["film_simulation"] == 0x45

    def test_committed_js_fixture_matches_the_served_payload(self) -> None:
        committed = json.loads(_FIXTURE.read_text())

        assert committed == camera_queries.client_camera_profile()
