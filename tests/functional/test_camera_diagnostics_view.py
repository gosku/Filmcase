from src.domain.camera import ptp_device


class TestCameraDiagnostics:
    def test_renders_the_diagnostics_page(self, client):
        response = client.get("/settings/camera-diagnostics/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "Camera diagnostics" in content

    def test_exposes_the_fujifilm_vendor_id_to_the_probe_script(self, client):
        response = client.get("/settings/camera-diagnostics/")

        content = response.content.decode()
        assert f"const FUJIFILM_VENDOR_ID = {ptp_device.FUJIFILM_VENDOR_ID};" in content

    def test_labels_the_vendor_id_in_hexadecimal_for_the_reader(self, client):
        response = client.get("/settings/camera-diagnostics/")

        assert f"0x{ptp_device.FUJIFILM_VENDOR_ID:04X}" in response.content.decode()

    def test_highlights_the_camera_diagnostics_tab_in_the_sidebar(self, client):
        response = client.get("/settings/camera-diagnostics/")

        content = response.content.decode()
        assert 'settings-nav__item--active">Camera Diagnostics' in content

    def test_reports_every_probe_step_the_push_path_depends_on(self, client):
        response = client.get("/settings/camera-diagnostics/")

        content = response.content.decode()
        for check_id in ("check-secure", "check-webusb", "check-open", "check-endpoints", "check-claim"):
            assert check_id in content


class TestCameraDiagnosticsPTPSession:
    def test_reports_a_ptp_session_step(self, client):
        # The steps above it only prove the browser can reach the device. This
        # one proves the camera will hold a PTP conversation, which is what the
        # push path actually depends on.
        response = client.get("/settings/camera-diagnostics/")

        assert "check-session" in response.content.decode()

    def test_loads_the_transport_as_a_module(self, client):
        response = client.get("/settings/camera-diagnostics/")

        content = response.content.decode()
        assert '<script type="module">' in content
        assert "/static/js/camera/vendor/ptp_usb_device.js" in content

    def test_does_not_carry_its_own_endpoint_discovery(self, client):
        # The page used to define findBulkInterface itself. Two versions of
        # endpoint discovery is the drift this port exists to avoid, so it now
        # imports the transport's.
        content = client.get("/settings/camera-diagnostics/").content.decode()

        assert "function findBulkInterface" not in content
        assert "_findBulkInterface" in content

    def test_points_at_the_client_config_endpoint(self, client):
        # The transport needs the timing settings, and fetching them on load
        # rather than on click keeps the user gesture intact for requestDevice.
        content = client.get("/settings/camera-diagnostics/").content.decode()

        assert "/camera/client-config.json" in content


class TestDiagnosticsAssets:
    def test_the_transport_module_is_served(self, client):
        # A module that 404s makes the whole page silently inert, and the page
        # is what a user is told to open when nothing works.
        response = client.get("/static/js/camera/vendor/ptp_usb_device.js")

        assert response.status_code == 200

    def test_the_modules_it_imports_are_served(self, client):
        for path in (
            "/static/js/camera/vendor/ptp_device.js",
            "/static/js/camera/vendor/events.js",
        ):
            assert client.get(path).status_code == 200, path
