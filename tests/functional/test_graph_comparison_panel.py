import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmRecipeFactory, ImageFactory

_URL = "/recipes/graph/comparison/"


def _recipe(**kwargs):
    defaults = {
        "film_simulation": "Provia",
        "white_balance_red": 0,
        "white_balance_blue": 0,
    }
    defaults.update(kwargs)
    return FujifilmRecipeFactory(**defaults)


def _get(client, *recipes):
    return client.get(_URL, {"ids": ",".join(str(r.pk) for r in recipes)})


def _soup(response):
    return BeautifulSoup(response.content, "html.parser")


def _changed_rows(response):
    return _soup(response).find_all(class_="graph-panel__row--changed")


def _row_labels(response, class_name):
    return [
        row.find(class_="graph-panel__key").get_text(strip=True)
        for row in _soup(response).find_all(class_=class_name)
    ]


@pytest.mark.django_db
class TestComparisonPanelBadRequests:
    def test_missing_ids_is_rejected(self, client):
        assert client.get(_URL).status_code == 400

    def test_non_numeric_ids_are_rejected(self, client):
        assert client.get(_URL, {"ids": "abc,def"}).status_code == 400

    def test_unknown_ids_are_a_404(self, client):
        assert client.get(_URL, {"ids": "999999"}).status_code == 404


@pytest.mark.django_db
class TestComparisonPanelReferenceState:
    def test_a_single_id_renders_the_reference_on_its_own(self, client):
        recipe = _recipe(name="Root")

        response = _get(client, recipe)

        assert "Recipe of reference" in response.content.decode()

    def test_reference_state_has_no_comparison_controls(self, client):
        recipe = _recipe(name="Root")

        response = _get(client, recipe)

        html = response.content.decode()
        assert "property-filter" not in html
        assert "Compare images" not in html

    def test_reference_meta_names_the_film_simulation_and_image_count(self, client):
        recipe = _recipe(name="Root", film_simulation="Velvia")
        ImageFactory.create_batch(3, fujifilm_recipe=recipe)

        response = _get(client, recipe)

        meta = _soup(response).find(class_="graph-panel__reference-meta").get_text(strip=True)
        assert "Velvia" in meta
        assert "3 images" in meta

    def test_image_count_is_singular_for_one_image(self, client):
        recipe = _recipe(name="Root")
        ImageFactory(fujifilm_recipe=recipe)

        response = _get(client, recipe)

        assert "1 image" in _soup(response).find(class_="graph-panel__reference-meta").get_text()

    def test_every_property_gets_a_row(self, client):
        recipe = _recipe(name="Root")

        response = _get(client, recipe)

        assert len(_soup(response).find_all(class_="graph-panel__row--reference")) > 0

    def test_rows_reference_an_icon(self, client):
        recipe = _recipe(name="Root")

        response = _get(client, recipe)

        uses = _soup(response).find_all("use")
        assert all(u.get("href", "").startswith("#prop-") for u in uses)
        assert len(uses) > 0


@pytest.mark.django_db
class TestComparisonPanelComparisonState:
    def test_two_ids_render_the_comparison(self, client):
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        assert "Comparing with" in response.content.decode()

    def test_both_recipe_names_are_shown(self, client):
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        names = [el.get_text(strip=True) for el in _soup(response).find_all(class_="graph-panel__card-name")]
        assert names == ["Root", "Other"]

    def test_a_changed_property_shows_both_values(self, client):
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        row = next(r for r in _changed_rows(response) if "Grain" in r.get_text())
        assert row.find(class_="graph-panel__from").get_text(strip=True) == "Off"
        assert row.find(class_="graph-panel__to").get_text(strip=True) == "Strong"

    def test_unchanged_properties_are_still_listed(self, client):
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        assert "Film Simulation" in _row_labels(response, "graph-panel__row--unchanged")

    def test_the_changed_count_is_shown_on_the_filter(self, client):
        reference = _recipe(name="Root", grain_roughness="Off", grain_size="Off")
        compared = _recipe(name="Other", grain_roughness="Strong", grain_size="Large")

        response = _get(client, reference, compared)

        label = _soup(response).select_one('#property-filter [data-properties="changes"]').get_text(strip=True)
        assert "2" in label

    def test_groups_carry_their_changed_count_for_filtering(self, client):
        # The client-side filter hides groups that would be left empty, so the
        # count has to be in the markup.
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        groups = _soup(response).find_all(class_="graph-panel__group")
        assert all(g.has_attr("data-changed-count") for g in groups)
        assert any(g["data-changed-count"] != "0" for g in groups)

    def test_each_card_links_to_its_own_recipe(self, client):
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        hrefs = [a["href"] for a in _soup(response).find_all("a", class_="graph-panel__link")]
        assert f"/recipes/{reference.pk}/" in hrefs
        assert f"/recipes/{compared.pk}/" in hrefs


@pytest.mark.django_db
class TestComparisonPanelDeltaBreakdown:
    def test_a_single_hop_has_no_breakdown(self, client):
        # The property list already says everything that changed.
        reference = _recipe(name="Root", grain_roughness="Off")
        compared = _recipe(name="Other", grain_roughness="Strong")

        response = _get(client, reference, compared)

        assert "Delta breakdown" not in response.content.decode()

    def test_a_multi_hop_path_gets_a_timeline(self, client):
        reference = _recipe(name="Root", grain_roughness="Off", grain_size="Off")
        middle = _recipe(name="Middle", grain_roughness="Strong", grain_size="Off")
        compared = _recipe(name="Other", grain_roughness="Strong", grain_size="Large")

        response = _get(client, reference, middle, compared)

        assert "Delta breakdown" in response.content.decode()

    def test_the_timeline_has_one_node_per_hop(self, client):
        reference = _recipe(name="Root", grain_roughness="Off", grain_size="Off")
        middle = _recipe(name="Middle", grain_roughness="Strong", grain_size="Off")
        compared = _recipe(name="Other", grain_roughness="Strong", grain_size="Large")

        response = _get(client, reference, middle, compared)

        assert len(_soup(response).find_all(class_="graph-timeline__node")) == 3

    def test_the_first_timeline_node_is_the_starting_point(self, client):
        reference = _recipe(name="Root", grain_roughness="Off", grain_size="Off")
        middle = _recipe(name="Middle", grain_roughness="Strong", grain_size="Off")
        compared = _recipe(name="Other", grain_roughness="Strong", grain_size="Large")

        response = _get(client, reference, middle, compared)

        first = _soup(response).find(class_="graph-timeline__node")
        assert "starting point" in first.get_text()

    def test_later_nodes_list_their_own_changes(self, client):
        reference = _recipe(name="Root", grain_roughness="Off", grain_size="Off")
        middle = _recipe(name="Middle", grain_roughness="Strong", grain_size="Off")
        compared = _recipe(name="Other", grain_roughness="Strong", grain_size="Large")

        response = _get(client, reference, middle, compared)

        changes = _soup(response).find_all(class_="graph-timeline__change-key")
        assert "Grain" in [c.get_text(strip=True) for c in changes]


@pytest.mark.django_db
class TestGraphPagesRenderThePanelOnLoad:
    def test_network_page_embeds_the_reference_panel(self, client):
        _recipe(name="Root")

        response = client.get("/recipes/graph/", {"film_sim": "Provia"})

        assert "Recipe of reference" in response.content.decode()

    def test_per_recipe_page_embeds_the_reference_panel(self, client):
        recipe = _recipe(name="Root")

        response = client.get(f"/recipes/graph/{recipe.pk}/")

        assert "Recipe of reference" in response.content.decode()

    def test_the_icon_sprite_is_included_once(self, client):
        _recipe(name="Root")

        response = client.get("/recipes/graph/", {"film_sim": "Provia"})

        assert response.content.decode().count('id="prop-film-sim"') == 1

    def test_json_response_carries_the_rendered_panel(self, client):
        import json

        _recipe(name="Root")

        response = client.get(
            "/recipes/graph/", {"film_sim": "Provia"}, HTTP_ACCEPT="application/json",
        )

        assert "graph-panel__header" in json.loads(response.content)["panel_html"]
