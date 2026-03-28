import pytest
from bs4 import BeautifulSoup
from django.test import override_settings
from django.utils import timezone

from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestGalleryResultsView:
    def test_filters_images_by_recipe_name(self, client):
        # Arrange: 2 recipes, 3 images (2 for recipe_a, 1 for recipe_b)
        recipe_a = FujifilmRecipeFactory(name="Classic Chrome Recipe", film_simulation="Classic Chrome")
        recipe_b = FujifilmRecipeFactory(name="Velvia Recipe", film_simulation="Velvia")
        ImageFactory(filename="fav.jpg",    fujifilm_recipe=recipe_a, is_favorite=True)
        ImageFactory(filename="normal.jpg", fujifilm_recipe=recipe_a, is_favorite=False)
        ImageFactory(fujifilm_recipe=recipe_b)

        # Act: filter by recipe_a id
        response = client.get("/images/results/", {"recipe_id": recipe_a.id})

        assert response.status_code == 200

        soup = BeautifulSoup(response.content, "html.parser")
        cards = soup.find_all(class_="image-card")

        # Only the 2 images belonging to recipe_a are shown
        assert len(cards) == 2

        # Favorite image appears first, then non-favorite
        filenames = [card.find(class_="image-filename").text.strip() for card in cards]
        assert filenames == ["fav.jpg", "normal.jpg"]

        # Favorite card carries the favourite marker; non-favourite does not
        assert cards[0].find(class_="image-favorite") is not None
        assert cards[1].find(class_="image-favorite") is None

        # Both cards show the recipe name
        assert cards[0].find(class_="image-recipe") is not None
        assert cards[1].find(class_="image-recipe") is not None


@pytest.mark.django_db
class TestGalleryInfiniteScroll:
    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_first_page_contains_page_size_images(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "1"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all(class_="image-card")) == 2

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_second_page_contains_remaining_images(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "2"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all(class_="image-card")) == 1

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_sentinel_present_when_more_pages(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = client.get("/images/results/")

        soup = BeautifulSoup(response.content, "html.parser")
        sentinel = soup.find(class_="infinite-scroll-sentinel")
        assert sentinel is not None

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_sentinel_absent_on_last_page(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "2"})

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="infinite-scroll-sentinel") is None

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_sentinel_absent_when_single_page(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory(fujifilm_recipe=recipe)

        response = client.get("/images/results/")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="infinite-scroll-sentinel") is None

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_sentinel_points_to_next_page(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(5, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "1"})

        soup = BeautifulSoup(response.content, "html.parser")
        sentinel = soup.find(class_="infinite-scroll-sentinel")
        assert sentinel is not None
        assert sentinel["hx-trigger"] == "intersect root:.gallery-scroll"
        assert sentinel["hx-swap"] == "outerHTML"
        assert sentinel["hx-target"] == "#load-more-sentinel"
        assert '"page": "2"' in sentinel["hx-vals"]

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_sentinel_on_middle_page_points_to_next(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(5, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "2"})

        soup = BeautifulSoup(response.content, "html.parser")
        sentinel = soup.find(class_="infinite-scroll-sentinel")
        assert sentinel is not None
        assert '"page": "3"' in sentinel["hx-vals"]

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_out_of_range_page_returns_last_page(self, client):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = client.get("/images/results/", {"page": "999"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        # Last page has 1 image; django's get_page() clamps to last page
        assert len(soup.find_all(class_="image-card")) == 1

    @override_settings(GALLERY_PAGE_SIZE=2)
    def test_page_param_absent_from_filter_change_url(self, client):
        """Filter changes reset to page 1; the page param should not be in the URL."""
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        # Simulate an HTMX filter-change request (no page param)
        response = client.get("/images/", {"favorites_first": "1"}, HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        # First page worth of images returned
        assert len(soup.find_all(class_="image-card")) == 2
        # Sentinel present since there is a second page
        assert soup.find(class_="infinite-scroll-sentinel") is not None


@pytest.mark.django_db
class TestWBRedBlueFilters:
    def test_gallery_loads_without_error_when_wb_red_blue_recipes_exist(self, client):
        recipe = FujifilmRecipeFactory(white_balance_red=3, white_balance_blue=-2)
        ImageFactory(fujifilm_recipe=recipe)

        response = client.get("/images/")

        assert response.status_code == 200

    def test_filters_images_by_white_balance_red(self, client):
        recipe_r3 = FujifilmRecipeFactory(white_balance_red=3)
        recipe_r0 = FujifilmRecipeFactory(white_balance_red=0)
        ImageFactory(filename="red3.jpg", fujifilm_recipe=recipe_r3)
        ImageFactory(filename="red0.jpg", fujifilm_recipe=recipe_r0)

        response = client.get("/images/results/", {"white_balance_red": "3"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        filenames = [c.find(class_="image-filename").text.strip() for c in soup.find_all(class_="image-card")]
        assert filenames == ["red3.jpg"]

    def test_filters_images_by_white_balance_blue(self, client):
        recipe_b2 = FujifilmRecipeFactory(white_balance_blue=2)
        recipe_b0 = FujifilmRecipeFactory(white_balance_blue=0)
        ImageFactory(filename="blue2.jpg", fujifilm_recipe=recipe_b2)
        ImageFactory(filename="blue0.jpg", fujifilm_recipe=recipe_b0)

        response = client.get("/images/results/", {"white_balance_blue": "2"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        filenames = [c.find(class_="image-filename").text.strip() for c in soup.find_all(class_="image-card")]
        assert filenames == ["blue2.jpg"]


@pytest.mark.django_db
class TestFavoritesFirstToggle:
    """A favorite (older) image and a non-favourite (newer) image are created.
    With the toggle enabled the favourite must come first; with it disabled the
    newer image must come first."""

    def setup_method(self):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        now = timezone.now()
        ImageFactory(
            filename="favorite_older.jpg",
            fujifilm_recipe=recipe,
            is_favorite=True,
            taken_at=now - timezone.timedelta(days=1),
        )
        ImageFactory(
            filename="nonfavorite_newer.jpg",
            fujifilm_recipe=recipe,
            is_favorite=False,
            taken_at=now,
        )

    def _filenames(self, response):
        soup = BeautifulSoup(response.content, "html.parser")
        return [card.find(class_="image-filename").text.strip() for card in soup.find_all(class_="image-card")]

    def test_favorites_shown_first_when_toggle_enabled(self, client):
        response = client.get("/images/results/", {"favorites_first": "1"})

        assert response.status_code == 200
        assert self._filenames(response) == ["favorite_older.jpg", "nonfavorite_newer.jpg"]

    def test_newest_shown_first_when_toggle_disabled(self, client):
        response = client.get("/images/results/", {"favorites_first": "0"})

        assert response.status_code == 200
        assert self._filenames(response) == ["nonfavorite_newer.jpg", "favorite_older.jpg"]

    def test_favorites_shown_first_by_default(self, client):
        response = client.get("/images/results/")

        assert response.status_code == 200
        assert self._filenames(response) == ["favorite_older.jpg", "nonfavorite_newer.jpg"]
