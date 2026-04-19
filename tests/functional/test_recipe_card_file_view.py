import pytest

from tests.factories import RecipeCardFactory


@pytest.mark.django_db
class TestRecipeCardFile:
    def test_returns_200_for_existing_card(self, client, tmp_path):
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"\xff\xd8\xff")
        card = RecipeCardFactory(filepath=str(filepath))
        response = client.get(f"/recipes/card/{card.pk}/file/")
        assert response.status_code == 200

    def test_returns_404_for_missing_card(self, client):
        response = client.get("/recipes/card/99999/file/")
        assert response.status_code == 404

    def test_content_type_is_jpeg(self, client, tmp_path):
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(b"\xff\xd8\xff")
        card = RecipeCardFactory(filepath=str(filepath))
        response = client.get(f"/recipes/card/{card.pk}/file/")
        assert response["Content-Type"] == "image/jpeg"

    def test_response_body_matches_file_content(self, client, tmp_path):
        content = b"\xff\xd8\xff\xe0" + b"\x00" * 100
        filepath = tmp_path / "card.jpg"
        filepath.write_bytes(content)
        card = RecipeCardFactory(filepath=str(filepath))
        response = client.get(f"/recipes/card/{card.pk}/file/")
        assert b"".join(response.streaming_content) == content
