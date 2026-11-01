"""
Regenerate xt2_profile.json, the served X-T2 layout shared by the Python and
JavaScript backup codecs.

    FILMCASE_ENV_FILE=/dev/null .venv/bin/python tests/fixtures/camera/generate_xt2_profile.py

This is the client's copy of src.data.camera.constants_xt2, exactly as
CameraClientConfig serves it. The JS codec is asserted against the same
committed blob fixture as the Python one using this layout, so a diff here means
the X-T2 byte map the browser runs on changed. Regenerate deliberately; a Python
test fails until the committed fixture matches the live payload.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parents[3]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.config.settings")

import django  # noqa: E402

django.setup()

from src.domain.camera import queries as camera_queries  # noqa: E402

HERE = pathlib.Path(__file__).parent
OUT = HERE / "xt2_profile.json"


def main() -> None:
    payload = camera_queries.client_camera_profile()
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
