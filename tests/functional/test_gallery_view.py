import pytest
from django.urls import reverse

from tests.factories import FujifilmRecipeFactory, ImageFactory


def _get(client):
    return client.get(reverse("gallery"))


@pytest.mark.django_db
class TestGalleryViewLayoutControls:
    def test_returns_200(self, client):
        response = _get(client)

        assert response.status_code == 200

    def test_renders_grid_and_compact_view_switcher(self, client):
        response = _get(client)

        content = response.content.decode()
        assert 'data-view-mode="grid"' in content
        assert 'data-view-mode="compact"' in content

    def test_renders_label_mode_control(self, client):
        response = _get(client)

        content = response.content.decode()
        assert 'data-label-mode="hover"' in content
        assert 'data-label-mode="always"' in content

    def test_renders_thumbnail_size_slider(self, client):
        response = _get(client)

        content = response.content.decode()
        assert 'id="size-slider"' in content
        assert 'type="range"' in content

    def test_loads_compact_gallery_script(self, client):
        response = _get(client)

        assert "compact-gallery.js" in response.content.decode()

    def test_gallery_container_defaults_to_grid_layout(self, client):
        response = _get(client)

        assert 'id="gallery-results" class="layout-grid' in response.content.decode()


@pytest.mark.django_db
class TestGalleryViewCompactOverlay:
    def test_each_card_renders_a_compact_overlay(self, client):
        ImageFactory(fujifilm_recipe=FujifilmRecipeFactory())

        response = _get(client)

        assert 'class="image-overlay"' in response.content.decode()

    def test_overlay_shows_the_recipe_name(self, client):
        recipe = FujifilmRecipeFactory(name="Kodak Portra 400 (v4)")
        ImageFactory(fujifilm_recipe=recipe)

        response = _get(client)

        content = response.content.decode()
        assert "image-overlay-name" in content
        assert "Kodak Portra 400 (v4)" in content

    def test_overlay_falls_back_to_film_simulation_without_a_name(self, client):
        recipe = FujifilmRecipeFactory(name="", film_simulation="Classic Negative")
        ImageFactory(fujifilm_recipe=recipe)

        response = _get(client)

        assert "Classic Negative" in response.content.decode()

    def test_overlay_shows_rating_stars_when_rated(self, client):
        ImageFactory(fujifilm_recipe=FujifilmRecipeFactory(), rating=3)

        response = _get(client)

        content = response.content.decode()
        assert "image-overlay-rating" in content
        assert "★★★" in content
