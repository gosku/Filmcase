import pytest
from django.urls import reverse

from src.data import models
from tests.factories import (
    FujifilmRecipeFactory,
    RecipeCollectionFactory,
    RecipeCollectionMemberFactory,
)


@pytest.mark.django_db
class TestCollectionsList:
    def test_renders_the_list_page(self, client):
        RecipeCollectionFactory(name="Street Mono")

        response = client.get(reverse("recipes-collections"))

        assert response.status_code == 200
        assert b"Street Mono" in response.content

    def test_htmx_request_returns_only_the_cards(self, client):
        RecipeCollectionFactory(name="Street Mono")

        response = client.get(reverse("recipes-collections"), HTTP_HX_REQUEST="true")

        assert response.status_code == 200
        assert b"Street Mono" in response.content
        assert b"<html" not in response.content

    def test_filters_by_collection_name(self, client):
        RecipeCollectionFactory(name="Street Mono")
        RecipeCollectionFactory(name="Golden Hour")

        response = client.get(reverse("recipes-collections"), {"name_search": "golden"})

        assert b"Golden Hour" in response.content
        assert b"Street Mono" not in response.content


@pytest.mark.django_db
class TestCollectionDetail:
    def test_permalink_renders_the_list_with_the_overlay(self, client):
        group = RecipeCollectionFactory(name="Street Mono")
        RecipeCollectionMemberFactory(
            group=group, recipe=FujifilmRecipeFactory(name="Kodak Tri-X")
        )

        response = client.get(reverse("recipe-collection-detail", args=[group.pk]))

        assert response.status_code == 200
        # Full page (list shell) with the overlay rendered on top.
        assert b"<html" in response.content
        assert b"collection-detail-overlay" in response.content
        assert b"Kodak Tri-X" in response.content

    def test_htmx_request_returns_only_the_overlay(self, client):
        group = RecipeCollectionFactory(name="Street Mono")
        RecipeCollectionMemberFactory(
            group=group, recipe=FujifilmRecipeFactory(name="Kodak Tri-X")
        )

        response = client.get(
            reverse("recipe-collection-detail", args=[group.pk]), HTTP_HX_REQUEST="true"
        )

        assert response.status_code == 200
        assert b"Kodak Tri-X" in response.content
        assert b"<html" not in response.content

    def test_returns_404_for_missing_collection(self, client):
        response = client.get(reverse("recipe-collection-detail", args=[999]))

        assert response.status_code == 404


@pytest.mark.django_db
class TestCreateCollection:
    def test_get_renders_the_form(self, client):
        response = client.get(reverse("create-collection"))

        assert response.status_code == 200
        assert b"New collection" in response.content

    def test_post_creates_and_redirects_to_detail(self, client):
        r1 = FujifilmRecipeFactory()
        r2 = FujifilmRecipeFactory()

        response = client.post(
            reverse("create-collection"),
            {"name": "Street Mono", "recipe_ids": [r2.pk, r1.pk]},
        )

        group = models.RecipeGroup.objects.get(
            name="Street Mono", group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION
        )
        assert response.status_code == 302
        assert response.url == reverse("recipe-collection-detail", args=[group.pk])
        order = list(
            models.RecipeGroupMember.objects.filter(group_id=group.pk)
            .order_by("position").values_list("recipe_id", flat=True)
        )
        assert order == [r2.pk, r1.pk]

    def test_post_with_duplicate_name_re_renders_with_error(self, client):
        RecipeCollectionFactory(name="Taken")

        response = client.post(reverse("create-collection"), {"name": "taken"})

        assert response.status_code == 200
        assert b"already exists" in response.content
        assert models.RecipeGroup.objects.filter(
            group_type=models.RecipeGroup.GROUP_TYPE_COLLECTION
        ).count() == 1


@pytest.mark.django_db
class TestEditCollection:
    def test_get_renders_the_form_with_current_name(self, client):
        group = RecipeCollectionFactory(name="Old Name")

        response = client.get(reverse("edit-collection", args=[group.pk]))

        assert response.status_code == 200
        assert b"Old Name" in response.content

    def test_get_returns_404_for_missing_collection(self, client):
        response = client.get(reverse("edit-collection", args=[999]))

        assert response.status_code == 404

    def test_post_updates_and_redirects(self, client):
        group = RecipeCollectionFactory(name="Old")
        recipe = FujifilmRecipeFactory()

        response = client.post(
            reverse("edit-collection", args=[group.pk]),
            {"name": "New", "recipe_ids": [recipe.pk]},
        )

        assert response.status_code == 302
        group.refresh_from_db()
        assert group.name == "New"


@pytest.mark.django_db
class TestDeleteCollection:
    def test_post_deletes_and_redirects_to_list(self, client):
        group = RecipeCollectionFactory(name="Set")

        response = client.post(reverse("delete-collection", args=[group.pk]))

        assert response.status_code == 302
        assert response.url == reverse("recipes-collections")
        assert not models.RecipeGroup.objects.filter(pk=group.pk).exists()

    def test_post_returns_404_for_missing_collection(self, client):
        response = client.post(reverse("delete-collection", args=[999]))

        assert response.status_code == 404


@pytest.mark.django_db
class TestCollectionRecipeSearch:
    def test_returns_matching_recipes(self, client):
        FujifilmRecipeFactory(name="Kodak Tri-X")
        FujifilmRecipeFactory(name="Velvia Punch")

        response = client.get(
            reverse("collection-recipe-search"), {"name_search": "tri-x"}
        )

        assert response.status_code == 200
        assert b"Kodak Tri-X" in response.content
        assert b"Velvia Punch" not in response.content
