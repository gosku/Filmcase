import pytest


@pytest.mark.django_db
class TestRootRedirect:
    def test_root_redirects_to_recipes(self, client):
        response = client.get("/")

        assert response.status_code == 302
        assert response["Location"] == "/recipes/"
