import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory


def _toggle_options(response):
    """
    Return [(label, is_active, is_link)] for the Explorer / Graph toggle.
    """
    soup = BeautifulSoup(response.content, "html.parser")
    toggle = soup.find(class_="segmented-toggle")
    assert toggle is not None, "the page is missing the Explorer / Graph toggle"
    return [
        (
            option.get_text(strip=True),
            "segmented-toggle__option--active" in option.get("class", []),
            option.name == "a",
        )
        for option in toggle.find_all(class_="segmented-toggle__option")
    ]


def _urls(recipe):
    return {
        "explorer": "/recipes/",
        "detail": f"/recipes/{recipe.pk}/",
        "graph": "/recipes/graph/",
        "recipe_graph": f"/recipes/graph/{recipe.pk}/",
    }


@pytest.mark.django_db
class TestSectionToggleIsSharedAcrossRecipePages:
    @pytest.mark.parametrize("page", ["explorer", "detail", "graph", "recipe_graph"])
    def test_page_renders_both_options(self, client, page):
        recipe = FujifilmRecipeFactory()

        response = client.get(_urls(recipe)[page])

        assert [label for label, _, _ in _toggle_options(response)] == ["Explorer", "Graph"]

    @pytest.mark.parametrize(
        "page,expected_active",
        [
            ("explorer", "Explorer"),
            ("detail", "Explorer"),
            ("graph", "Graph"),
            ("recipe_graph", "Graph"),
        ],
    )
    def test_correct_option_is_active(self, client, page, expected_active):
        recipe = FujifilmRecipeFactory()

        response = client.get(_urls(recipe)[page])

        active = [label for label, is_active, _ in _toggle_options(response) if is_active]
        assert active == [expected_active]

    @pytest.mark.parametrize("page", ["explorer", "detail", "graph", "recipe_graph"])
    def test_active_option_is_not_a_link(self, client, page):
        # The half you are already on should not navigate anywhere.
        recipe = FujifilmRecipeFactory()

        response = client.get(_urls(recipe)[page])

        active = [is_link for _, is_active, is_link in _toggle_options(response) if is_active]
        assert active == [False]

    @pytest.mark.parametrize("page", ["explorer", "detail", "graph", "recipe_graph"])
    def test_inactive_option_is_a_link(self, client, page):
        recipe = FujifilmRecipeFactory()

        response = client.get(_urls(recipe)[page])

        inactive = [is_link for _, is_active, is_link in _toggle_options(response) if not is_active]
        assert inactive == [True]

    @pytest.mark.parametrize("page", ["explorer", "detail", "graph", "recipe_graph"])
    def test_old_duplicated_nav_class_is_gone(self, client, page):
        recipe = FujifilmRecipeFactory()

        response = client.get(_urls(recipe)[page])

        assert "sidebar-nav" not in response.content.decode()
