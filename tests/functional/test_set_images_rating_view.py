from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.data import models
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestSetImagesRatingViewMethodGuard:
    def test_get_returns_405(self, client) -> None:
        response = client.get("/images/set-rating/")
        assert response.status_code == 405


@pytest.mark.django_db
class TestSetImagesRatingGalleryPresence:
    def test_set_rating_action_button_is_in_actions_dropdown(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find("button", id="ms-set-rating-btn") is not None

    def test_set_rating_modal_is_in_page(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(id="set-rating-overlay") is not None

    def test_form_posts_to_correct_url(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form", id="set-rating-form")
        assert form is not None
        assert form.get("hx-post") == "/images/set-rating/"

    def test_picker_renders_a_star_per_rating_and_a_clear_button(self, client) -> None:
        response = client.get("/images/")
        soup = BeautifulSoup(response.content, "html.parser")
        picker = soup.find(id="set-rating-picker")
        assert picker is not None
        assert len(picker.find_all("button", class_="detail-rating-star")) == 5
        assert picker.find("button", class_="detail-rating-clear") is not None


@pytest.mark.django_db
class TestSetImagesRatingViewSuccess:
    def test_returns_200(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": 3})
        assert response.status_code == 200

    def test_rates_every_selected_image(self, client) -> None:
        images = [ImageFactory(rating=0) for _ in range(3)]
        client.post(
            "/images/set-rating/",
            {"image_ids": [image.pk for image in images], "rating": 4},
        )
        assert list(
            models.Image.objects.filter(pk__in=[image.pk for image in images]).values_list("rating", flat=True)
        ) == [4, 4, 4]

    def test_response_shows_rated_count(self, client) -> None:
        images = [ImageFactory(rating=0) for _ in range(2)]
        response = client.post(
            "/images/set-rating/",
            {"image_ids": [image.pk for image in images], "rating": 2},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert "2 image" in soup.get_text().lower()

    def test_marks_all_succeeded_when_all_rated(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": 3})
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "true"}) is not None

    def test_rating_zero_clears_the_rating(self, client) -> None:
        image = ImageFactory(rating=4)
        client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": 0})
        image.refresh_from_db()
        assert image.rating == 0


@pytest.mark.django_db
class TestSetImagesRatingViewPartialFailure:
    def test_missing_id_marks_not_all_succeeded(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post(
            "/images/set-rating/",
            {"image_ids": [image.pk, image.pk + 1000], "rating": 3},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None

    def test_missing_id_shows_not_found_message(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post(
            "/images/set-rating/",
            {"image_ids": [image.pk, image.pk + 1000], "rating": 3},
        )
        soup = BeautifulSoup(response.content, "html.parser")
        assert "could not be found" in soup.get_text().lower()


@pytest.mark.django_db
class TestSetImagesRatingViewBadRequest:
    def test_non_integer_image_ids_returns_400(self, client) -> None:
        response = client.post("/images/set-rating/", {"image_ids": ["abc"], "rating": 3})
        assert response.status_code == 400

    def test_non_integer_rating_returns_400(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": "x"})
        assert response.status_code == 400

    def test_out_of_range_rating_shows_error_message(self, client) -> None:
        image = ImageFactory(rating=0)
        response = client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": 6})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(attrs={"data-all-succeeded": "false"}) is not None
        image.refresh_from_db()
        assert image.rating == 0

    def test_unexpected_exception_shows_error_message(self, client) -> None:
        image = ImageFactory(rating=0)
        with patch(
            "src.interfaces.images.views.set_images_rating_uc.set_images_rating",
            side_effect=RuntimeError("boom"),
        ):
            response = client.post("/images/set-rating/", {"image_ids": [image.pk], "rating": 3})
        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert "unexpected" in soup.get_text().lower()
