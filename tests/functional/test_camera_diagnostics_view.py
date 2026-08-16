from src.domain.camera import ptp_device


class TestCameraDiagnostics:
    def test_renders_the_diagnostics_page(self, client):
        response = client.get("/camera/diagnostics/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Camera diagnostics" in content

    def test_exposes_the_fujifilm_vendor_id_to_the_probe_script(self, client):
        response = client.get("/camera/diagnostics/")

        content = response.content.decode()
        assert f"const FUJIFILM_VENDOR_ID = {ptp_device.FUJIFILM_VENDOR_ID};" in content

    def test_labels_the_vendor_id_in_hexadecimal_for_the_reader(self, client):
        response = client.get("/camera/diagnostics/")

        assert f"0x{ptp_device.FUJIFILM_VENDOR_ID:04X}" in response.content.decode()

    def test_highlights_the_camera_section_in_the_navigation(self, client):
        response = client.get("/camera/diagnostics/")

        assert "top-nav__link--active" in response.content.decode()

    def test_reports_every_probe_step_the_push_path_depends_on(self, client):
        response = client.get("/camera/diagnostics/")

        content = response.content.decode()
        for check_id in ("check-secure", "check-webusb", "check-open", "check-endpoints", "check-claim"):
            assert check_id in content
