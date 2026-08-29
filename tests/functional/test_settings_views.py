import pytest


@pytest.mark.django_db
class TestSettingsRedirect:
    def test_settings_redirects_to_library(self, client):
        response = client.get("/settings/")

        assert response.status_code == 302
        assert response["Location"] == "/settings/library/"
