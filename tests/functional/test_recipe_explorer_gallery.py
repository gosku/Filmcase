import pytest
from bs4 import BeautifulSoup
from django.test import override_settings

from tests.factories import FujifilmRecipeFactory, ImageFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_explorer(client, **params):
    return client.get("/recipes/", params)


def _get_results(client, **params):
    return client.get("/recipes/partial/results/", params)


def _cards(response):
    soup = BeautifulSoup(response.content, "html.parser")
    return soup.find_all(class_="recipe-card")


def _card_names(response):
    soup = BeautifulSoup(response.content, "html.parser")
    return [el.get_text(strip=True) for el in soup.find_all(class_="recipe-card__name")]


# ---------------------------------------------------------------------------
# Gallery rendering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipeExplorerGallery:
    def test_returns_200(self, client):
        response = _get_explorer(client)

        assert response.status_code == 200

    def test_recipe_cards_visible(self, client):
        FujifilmRecipeFactory()
        FujifilmRecipeFactory()

        response = _get_explorer(client)

        assert len(_cards(response)) == 2

    def test_named_recipe_shows_name_on_card(self, client):
        FujifilmRecipeFactory(name="Street Provia", film_simulation="Provia")

        response = _get_explorer(client)

        assert "Street Provia" in _card_names(response)

    def test_unnamed_recipe_shows_film_simulation_and_id_on_card(self, client):
        recipe = FujifilmRecipeFactory(name="", film_simulation="Velvia")

        response = _get_explorer(client)

        assert f"Velvia #{recipe.id}" in _card_names(response)

    def test_named_recipes_come_before_unnamed(self, client):
        unnamed = FujifilmRecipeFactory(name="", film_simulation="Provia")
        FujifilmRecipeFactory(name="Named One", film_simulation="Velvia")

        response = _get_explorer(client)

        names = _card_names(response)
        assert names.index("Named One") < names.index(f"Provia #{unnamed.id}")

    def test_named_recipe_with_fewer_images_beats_unnamed_with_more(self, client):
        named_few = FujifilmRecipeFactory(name="Named Few")
        unnamed_many = FujifilmRecipeFactory(name="", film_simulation="Velvia")
        ImageFactory.create_batch(5, fujifilm_recipe=unnamed_many)
        ImageFactory(fujifilm_recipe=named_few)

        response = _get_explorer(client)

        names = _card_names(response)
        assert names.index("Named Few") < names.index(f"Velvia #{unnamed_many.id}")

    def test_within_named_recipes_more_images_comes_first(self, client):
        few = FujifilmRecipeFactory(name="Few")
        many = FujifilmRecipeFactory(name="Many")
        ImageFactory.create_batch(5, fujifilm_recipe=many)
        ImageFactory(fujifilm_recipe=few)

        response = _get_explorer(client)

        names = _card_names(response)
        assert names.index("Many") < names.index("Few")


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipeExplorerFiltering:
    def test_film_simulation_filter_returns_only_matching_recipes(self, client):
        FujifilmRecipeFactory(name="Provia Recipe", film_simulation="Provia")
        FujifilmRecipeFactory(name="Velvia Recipe", film_simulation="Velvia")

        response = _get_explorer(client, film_simulation="Provia")

        names = _card_names(response)
        assert "Provia Recipe" in names
        assert "Velvia Recipe" not in names

    def test_multiple_values_for_same_field(self, client):
        FujifilmRecipeFactory(name="Provia Recipe", film_simulation="Provia")
        FujifilmRecipeFactory(name="Velvia Recipe", film_simulation="Velvia")
        FujifilmRecipeFactory(name="Astia Recipe", film_simulation="Astia")

        response = client.get("/recipes/?film_simulation=Provia&film_simulation=Velvia")

        names = _card_names(response)
        assert "Provia Recipe" in names
        assert "Velvia Recipe" in names
        assert "Astia Recipe" not in names

    def test_no_results_message_when_nothing_matches(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get_explorer(client, film_simulation="Velvia")

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="no-results") is not None

    def test_clear_filters_button_present(self, client):
        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="clear-filters-btn") is not None

    def test_clear_filters_href_points_to_explorer_root(self, client):
        response = _get_explorer(client, film_simulation="Provia")

        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="clear-filters-btn")
        assert btn is not None
        assert btn.get("href") == "/recipes/"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipeExplorerSidebar:
    def test_sidebar_shows_filter_options(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        sidebar = soup.find(id="recipe-sidebar-filters")
        assert sidebar is not None
        assert sidebar.find("input", {"value": "Provia"}) is not None

    def test_sidebar_counts_recipes_not_images(self, client):
        # 1 recipe with 5 images, 1 recipe with 1 image — same film_simulation
        # sidebar count must be 2 (recipes), not 6 (images)
        recipe_a = FujifilmRecipeFactory(film_simulation="Provia")
        recipe_b = FujifilmRecipeFactory(film_simulation="Provia")
        ImageFactory.create_batch(5, fujifilm_recipe=recipe_a)
        ImageFactory(fujifilm_recipe=recipe_b)

        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        provia_label = soup.find("input", {"name": "film_simulation", "value": "Provia"})
        assert provia_label is not None
        count_span = provia_label.find_next_sibling(class_="filter-option-count")
        assert count_span is not None
        assert count_span.get_text(strip=True) == "(2)"

    def test_selected_option_marked_as_checked(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = _get_explorer(client, film_simulation="Provia")

        soup = BeautifulSoup(response.content, "html.parser")
        provia_input = soup.find("input", {"name": "film_simulation", "value": "Provia"})
        assert provia_input is not None
        assert provia_input.has_attr("checked")


# ---------------------------------------------------------------------------
# HTMX partial responses
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipeExplorerHtmx:
    def test_htmx_request_returns_partial_without_doctype(self, client):
        response = client.get("/recipes/", HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert b"<!DOCTYPE" not in response.content

    def test_htmx_response_contains_oob_sidebar(self, client):
        FujifilmRecipeFactory(film_simulation="Provia")

        response = client.get("/recipes/", HTTP_HX_REQUEST="true")

        soup = BeautifulSoup(response.content, "html.parser")
        sidebar = soup.find(id="recipe-sidebar-filters")
        assert sidebar is not None
        assert sidebar.get("hx-swap-oob") == "true"


# ---------------------------------------------------------------------------
# Pagination / infinite scroll
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestRecipeExplorerPagination:
    @override_settings(RECIPE_EXPLORER_PAGE_SIZE=2)
    def test_sentinel_present_when_more_pages(self, client):
        FujifilmRecipeFactory.create_batch(3)

        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="infinite-scroll-sentinel") is not None

    @override_settings(RECIPE_EXPLORER_PAGE_SIZE=2)
    def test_sentinel_absent_on_last_page(self, client):
        FujifilmRecipeFactory.create_batch(2)

        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="infinite-scroll-sentinel") is None

    @override_settings(RECIPE_EXPLORER_PAGE_SIZE=2)
    def test_sentinel_points_to_page_2(self, client):
        FujifilmRecipeFactory.create_batch(3)

        response = _get_explorer(client)

        soup = BeautifulSoup(response.content, "html.parser")
        sentinel = soup.find(class_="infinite-scroll-sentinel")
        assert sentinel is not None
        assert '"page": "2"' in sentinel.get("hx-vals", "")

    @override_settings(RECIPE_EXPLORER_PAGE_SIZE=2)
    def test_scroll_endpoint_returns_partial(self, client):
        FujifilmRecipeFactory.create_batch(3)

        response = _get_results(client, page=2)

        assert response.status_code == 200
        assert b"<!DOCTYPE" not in response.content

    @override_settings(RECIPE_EXPLORER_PAGE_SIZE=2)
    def test_second_page_has_correct_recipes(self, client):
        # 3 recipes with 3, 2, 1 images respectively — page 2 should have the last one
        r1 = FujifilmRecipeFactory(name="Top")
        r2 = FujifilmRecipeFactory(name="Mid")
        r3 = FujifilmRecipeFactory(name="Last")
        ImageFactory.create_batch(3, fujifilm_recipe=r1)
        ImageFactory.create_batch(2, fujifilm_recipe=r2)
        ImageFactory(fujifilm_recipe=r3)

        response = _get_results(client, page=2)

        names = _card_names(response)
        assert "Last" in names
        assert "Top" not in names
        assert "Mid" not in names
