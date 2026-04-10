import pytest


@pytest.mark.django_db
class TestStaticFileView:
    def test_known_logo_returns_200(self, client):
        response = client.get("/static/images/classic-chrome.png")

        assert response.status_code == 200

    def test_known_logo_content_type_is_png(self, client):
        response = client.get("/static/images/classic-chrome.png")

        assert response["Content-Type"] == "image/png"

    def test_unknown_file_returns_404(self, client):
        response = client.get("/static/images/does-not-exist.png")

        assert response.status_code == 404

    def test_all_film_sim_logos_are_served(self, client):
        from src.domain.recipes.constants import FILM_SIM_LOGO

        for filename in FILM_SIM_LOGO.values():
            response = client.get(f"/static/images/{filename}")
            assert response.status_code == 200, f"/static/images/{filename} returned {response.status_code}"
