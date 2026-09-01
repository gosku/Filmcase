from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory


def _photo(*, folder_path, name, content=b"\xff\xd8abc"):
    path = folder_path / name
    path.write_bytes(content)
    return path


@pytest.mark.django_db
class TestRemoveImagesViewMethodGuard:
    def test_get_returns_405(self, client) -> None:
        response = client.get("/images/remove/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestRemoveImagesGalleryPresence:
    def test_remove_action_button_is_in_actions_dropdown(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("button", id="ms-remove-btn") is not None

    def test_remove_modal_is_in_page(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="remove-images-overlay") is not None

    def test_form_posts_to_correct_url(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="remove-images-form")
        assert form is not None
        assert form.get("hx-post") == "/images/remove/"

    def test_modal_warns_about_the_ignore_list(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        modal_text = soup.find(id="remove-images-modal-body").get_text().lower()
        assert "ignore list" in modal_text


@pytest.mark.django_db
class TestRemoveImagesViewSuccess:
    def test_returns_200(self, client, tmp_path) -> None:
        image = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        response = client.post("/images/remove/", {"image_ids": [image.pk]})
        assert response.status_code == 200

    def test_removes_every_selected_image(self, client, tmp_path) -> None:
        images = [
            ImageFactory(filepath=str(_photo(folder_path=tmp_path, name=f"{n}.jpg")))
            for n in range(3)
        ]
        client.post("/images/remove/", {"image_ids": [image.pk for image in images]})
        assert not models.Image.objects.filter(pk__in=[image.pk for image in images]).exists()

    def test_image_under_a_folder_is_added_to_the_ignore_list(self, client, tmp_path) -> None:
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        client.post("/images/remove/", {"image_ids": [image.pk]})

        ignored = models.IgnoredImage.objects.get(filepath=str(photo))
        assert ignored.reason == models.IgnoredImage.REASON_USER_REMOVED
        assert ignored.folder_id == folder.pk

    def test_image_under_no_folder_is_not_ignored(self, client, tmp_path) -> None:
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        client.post("/images/remove/", {"image_ids": [image.pk]})

        assert not models.IgnoredImage.objects.filter(filepath=str(photo)).exists()

    def test_keeps_the_file_on_disk(self, client, tmp_path) -> None:
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        client.post("/images/remove/", {"image_ids": [image.pk]})

        assert photo.exists()

    def test_marks_all_succeeded_when_all_removed(self, client, tmp_path) -> None:
        image = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        response = client.post("/images/remove/", {"image_ids": [image.pk]})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "true"}) is not None


@pytest.mark.django_db
class TestRemoveImagesViewPartialFailure:
    def test_missing_id_marks_not_all_succeeded(self, client, tmp_path) -> None:
        image = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        response = client.post(
            "/images/remove/",
            {"image_ids": [image.pk, image.pk + 1000]},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None

    def test_missing_id_shows_not_found_message(self, client, tmp_path) -> None:
        image = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        response = client.post(
            "/images/remove/",
            {"image_ids": [image.pk, image.pk + 1000]},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert "could not be found" in soup.get_text().lower()


@pytest.mark.django_db
class TestRemoveImagesViewBadRequest:
    def test_non_integer_image_ids_returns_400(self, client) -> None:
        response = client.post("/images/remove/", {"image_ids": ["abc"]})
        assert response.status_code == 400

    def test_unexpected_exception_shows_error_message(self, client, tmp_path) -> None:
        image = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        with patch(
            "src.interfaces.images.views.remove_images_uc.remove_images_from_gallery",
            side_effect=RuntimeError("boom"),
        ):
            response = client.post("/images/remove/", {"image_ids": [image.pk]})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "unexpected" in soup.get_text().lower()
