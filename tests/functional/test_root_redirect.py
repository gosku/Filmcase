import pytest


@pytest.mark.django_db
class TestRootRedirect:
    def test_root_redirects_to_gallery(self, client):
        response = client.get("/")

        assert response.status_code == 302
        assert response["Location"] == "/images/"
