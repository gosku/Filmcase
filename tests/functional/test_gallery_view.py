import pytest
from bs4 import BeautifulSoup
from django.test import override_settings
from django.utils import timezone

from tests.factories import FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestRecipeMultiSelect:
    def test_single_recipe_filter_returns_matching_images(self, client):
        recipe_a = FujifilmRecipeFactory(name="Recipe A")
        recipe_b = FujifilmRecipeFactory(name="Recipe B")
        ImageFactory(filename="a.jpg", fujifilm_recipe=recipe_a)
        ImageFactory(filename="b.jpg", fujifilm_recipe=recipe_b)

        response = client.get("/images/results/", {"recipe_id": recipe_a.id})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        filenames = {c.find(class_="image-filename").text.strip() for c in soup.find_all(class_="image-card")}
        assert filenames == {"a.jpg"}

    def test_two_recipe_ids_return_images_from_both(self, client):
        recipe_a = FujifilmRecipeFactory(name="Recipe A")
        recipe_b = FujifilmRecipeFactory(name="Recipe B")
        recipe_c = FujifilmRecipeFactory(name="Recipe C")
        ImageFactory(filename="a.jpg", fujifilm_recipe=recipe_a)
        ImageFactory(filename="b.jpg", fujifilm_recipe=recipe_b)
        ImageFactory(filename="c.jpg", fujifilm_recipe=recipe_c)

        response = client.get(f"/images/results/?recipe_id={recipe_a.id}&recipe_id={recipe_b.id}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        filenames = {c.find(class_="image-filename").text.strip() for c in soup.find_all(class_="image-card")}
        assert filenames == {"a.jpg", "b.jpg"}
        assert "c.jpg" not in filenames

    def test_full_page_renders_selected_recipe_options_as_selected(self, client):
        recipe = FujifilmRecipeFactory(name="My Recipe")
        ImageFactory.create_batch(51, fujifilm_recipe=recipe)

        response = client.get("/images/", {"recipe_id": str(recipe.id)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        option = soup.find("option", {"value": str(recipe.id)})
        assert option is not None
        assert option.has_attr("selected")

    def test_full_page_renders_recipe_select_as_multiple(self, client):
        recipe = FujifilmRecipeFactory(name="Named Recipe")
        ImageFactory(fujifilm_recipe=recipe)

        response = client.get("/images/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        recipe_select = soup.find("select", {"name": "recipe_id"})
        assert recipe_select is not None
        assert recipe_select.has_attr("multiple")

    def test_recipe_filter_combined_with_field_filter(self, client):
        recipe_provia = FujifilmRecipeFactory(name="Provia Recipe", film_simulation="Provia")
        recipe_velvia = FujifilmRecipeFactory(name="Velvia Recipe", film_simulation="Velvia")
        ImageFactory(filename="provia.jpg", fujifilm_recipe=recipe_provia)
        ImageFactory(filename="velvia.jpg", fujifilm_recipe=recipe_velvia)

        # Select both recipes but also filter by Provia — only provia.jpg should match
        response = client.get(
            f"/images/results/?recipe_id={recipe_provia.id}&recipe_id={recipe_velvia.id}&film_simulation=Provia"
        )

        soup = BeautifulSoup(response.content, "html.parser")
        filenames = {c.find(class_="image-filename").text.strip() for c in soup.find_all(class_="image-card")}
        assert filenames == {"provia.jpg"}


@pytest.mark.django_db
class TestClearFiltersButton:
    def test_clear_button_is_present_on_gallery_page(self, client):
        response = client.get("/images/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="clear-filters-btn")
        assert btn is not None

    def test_clear_button_links_to_gallery_without_filters(self, client):
        response = client.get("/images/", {"film_simulation": "Provia", "favorites_first": "1"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="clear-filters-btn")
        href = btn["href"]
        assert "film_simulation" not in href
        assert "recipe_id" not in href

    def test_clear_button_preserves_favorites_first_preference(self, client):
        response = client.get("/images/", {"favorites_first": "0"})

        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="clear-filters-btn")
        assert "favorites_first=0" in btn["href"]

    def test_following_clear_button_shows_all_images(self, client):
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia")
        recipe_b = FujifilmRecipeFactory(film_simulation="Velvia")
        ImageFactory(filename="a.jpg", fujifilm_recipe=recipe_a)
        ImageFactory(filename="b.jpg", fujifilm_recipe=recipe_b)

        # First apply a filter
        filtered = client.get("/images/results/", {"film_simulation": "Provia"})
        soup = BeautifulSoup(filtered.content, "html.parser")
        assert len(soup.find_all(class_="image-card")) == 1

        # Then navigate to the clear URL
        cleared = client.get("/images/")
        soup = BeautifulSoup(cleared.content, "html.parser")
        assert len(soup.find_all(class_="image-card")) == 2


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
class TestRatingFirstToggle:
    """Three images with ratings 0, 1, 2 where the highest-rated is the oldest.
    With the toggle enabled the highest-rated image must come first; with it
    disabled the newest image (rating 0) must come first."""

    def setup_method(self):
        recipe = FujifilmRecipeFactory(name="Test Recipe")
        now = timezone.now()
        ImageFactory(
            filename="rating2_oldest.jpg",
            fujifilm_recipe=recipe,
            rating=2,
            taken_at=now - timezone.timedelta(days=2),
        )
        ImageFactory(
            filename="rating1_middle.jpg",
            fujifilm_recipe=recipe,
            rating=1,
            taken_at=now - timezone.timedelta(days=1),
        )
        ImageFactory(
            filename="rating0_newest.jpg",
            fujifilm_recipe=recipe,
            rating=0,
            taken_at=now,
        )

    def _filenames(self, response):
        soup = BeautifulSoup(response.content, "html.parser")
        return [card.find(class_="image-filename").text.strip() for card in soup.find_all(class_="image-card")]

    def test_highest_rated_shown_first_when_toggle_enabled(self, client):
        response = client.get("/images/results/", {"rating_first": "1"})

        assert response.status_code == 200
        assert self._filenames(response) == ["rating2_oldest.jpg", "rating1_middle.jpg", "rating0_newest.jpg"]

    def test_newest_shown_first_when_toggle_disabled(self, client):
        response = client.get("/images/results/", {"rating_first": "0"})

        assert response.status_code == 200
        assert self._filenames(response) == ["rating0_newest.jpg", "rating1_middle.jpg", "rating2_oldest.jpg"]

    def test_highest_rated_shown_first_by_default(self, client):
        response = client.get("/images/results/")

        assert response.status_code == 200
        assert self._filenames(response) == ["rating2_oldest.jpg", "rating1_middle.jpg", "rating0_newest.jpg"]
