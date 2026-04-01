import pytest
from bs4 import BeautifulSoup
from django.test import override_settings

from tests.factories import ImageFactory


@pytest.mark.django_db
class TestRatingWidgetInDetailView:
    @override_settings(IMAGE_MAX_RATING=5)
    def test_rating_widget_is_in_detail_header(self, client):
        image = ImageFactory()

        response = client.get(f"/images/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        header = soup.find(class_="detail-header")
        assert header is not None
        assert header.find(class_="detail-rating") is not None

    @override_settings(IMAGE_MAX_RATING=5)
    def test_unrated_image_shows_no_active_stars(self, client):
        image = ImageFactory(rating=None)

        response = client.get(f"/images/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all(class_="detail-rating-star--active")) == 0

    @override_settings(IMAGE_MAX_RATING=5)
    def test_rated_image_shows_active_stars_up_to_rating(self, client):
        image = ImageFactory(rating=3)

        response = client.get(f"/images/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        active = soup.find_all(class_="detail-rating-star--active")
        assert len(active) == 3

    @override_settings(IMAGE_MAX_RATING=5)
    def test_widget_shows_one_star_button_per_max_rating(self, client):
        image = ImageFactory()

        response = client.get(f"/images/{image.id}/")

        soup = BeautifulSoup(response.content, "html.parser")
        all_stars = soup.find_all(class_="detail-rating-star")
        assert len(all_stars) == 5

    @override_settings(IMAGE_MAX_RATING=5)
    def test_clicking_star_returns_widget_with_correct_active_stars(self, client):
        image = ImageFactory(rating=None)

        response = client.post(f"/images/{image.id}/set-rating/", data={"rating": 4})

        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all(class_="detail-rating-star--active")) == 4

    @override_settings(IMAGE_MAX_RATING=5)
    def test_clear_button_returns_widget_with_no_active_stars(self, client):
        image = ImageFactory(rating=4)

        response = client.post(f"/images/{image.id}/set-rating/", data={"rating": 0})

        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all(class_="detail-rating-star--active")) == 0

    def test_set_rating_endpoint_returns_404_for_missing_image(self, client):
        response = client.post("/images/99999/set-rating/", data={"rating": 1})
        assert response.status_code == 404

    def test_set_rating_endpoint_rejects_get_request(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/set-rating/")
        assert response.status_code == 405
