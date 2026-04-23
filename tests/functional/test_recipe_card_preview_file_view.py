import pytest

from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestRecipeCardPreviewFile:
    def test_returns_200_for_existing_recipe(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/preview/file/")
        assert response.status_code == 200

    def test_content_type_is_jpeg(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/preview/file/")
        assert response["Content-Type"] == "image/jpeg"

    def test_returns_404_for_missing_recipe(self, client):
        response = client.get("/recipes/99999/card/preview/file/")
        assert response.status_code == 404

    def test_label_style_param_changes_output(self, client):
        recipe = FujifilmRecipeFactory()
        response_long = client.get(f"/recipes/{recipe.pk}/card/preview/file/?label_style=long")
        response_short = client.get(f"/recipes/{recipe.pk}/card/preview/file/?label_style=short")
        assert response_long.status_code == 200
        assert response_short.status_code == 200

    def test_response_is_a_non_empty_file(self, client):
        recipe = FujifilmRecipeFactory()
        response = client.get(f"/recipes/{recipe.pk}/card/preview/file/")
        content = b"".join(response.streaming_content)
        assert len(content) > 0
