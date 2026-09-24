from django import http, shortcuts, urls
from django.views import generic

from src.application.usecases.collections import create_collection as create_collection_uc
from src.application.usecases.collections import delete_collection as delete_collection_uc
from src.application.usecases.collections import update_collection as update_collection_uc
from src.interfaces import forms as interface_forms
from src.domain.recipes import queries as recipe_queries


def _recipe_ids_from_request(request: http.HttpRequest) -> list[int] | None:
    """Return the posted ordered recipe ids, or None when any is not an int."""
    try:
        return [int(value) for value in request.POST.getlist("recipe_ids")]
    except (ValueError, TypeError):
        return None


class CollectionsList(generic.View):
    """
    Display the collections list with filtering by collection name, recipe name
    and film simulation.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        name_search = request.GET.get("name_search", "").strip()
        recipe_name_search = request.GET.get("recipe_name_search", "").strip()
        film_simulations = request.GET.getlist("film_simulation")
        collections = recipe_queries.get_collection_summaries(
            name_search=name_search,
            recipe_name_search=recipe_name_search,
            film_simulations=film_simulations,
        )
        ctx = {
            "collections": collections,
            "filter_options": recipe_queries.get_collection_filter_options(
                selected_film_simulations=film_simulations
            ),
            "name_search": name_search,
            "recipe_name_search": recipe_name_search,
        }
        if request.headers.get("HX-Request"):
            return shortcuts.render(request, "recipes/partials/collection_cards.html", ctx)
        return shortcuts.render(request, "recipes/collections_list.html", ctx)


class CollectionDetail(generic.View):
    """
    Display a single collection as an overlay over the collections list.

    An htmx request returns just the overlay partial, so a card click opens it
    without a full page load. A direct visit to the permalink returns the list
    page with the overlay already rendered on top, so the link resolves on its
    own.

    :raises Http404: If no collection with the given id exists.
    """

    def get(self, request: http.HttpRequest, collection_id: int) -> http.HttpResponse:
        try:
            detail = recipe_queries.get_collection_detail(collection_id=collection_id)
        except recipe_queries.CollectionNotFound:
            raise http.Http404

        if request.headers.get("HX-Request"):
            return shortcuts.render(
                request, "recipes/partials/collection_detail.html", {"collection": detail}
            )

        return shortcuts.render(request, "recipes/collections_list.html", {
            "collections": recipe_queries.get_collection_summaries(),
            "filter_options": recipe_queries.get_collection_filter_options(),
            "name_search": "",
            "recipe_name_search": "",
            "detail": detail,
        })


class CreateCollection(generic.View):
    """
    Create a new collection.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        return shortcuts.render(request, "recipes/collection_form.html", {
            "mode": "create",
            "form": interface_forms.Collection(),
            "form_action": urls.reverse("create-collection"),
            "name_value": "",
            "selected_recipes": (),
        })

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        form = interface_forms.Collection(request.POST)
        recipe_ids = _recipe_ids_from_request(request)
        if recipe_ids is None:
            return http.HttpResponseBadRequest("recipe_ids must be integers")

        if form.is_valid():
            try:
                result = create_collection_uc.create_collection(
                    name=form.cleaned_data["name"], recipe_ids=recipe_ids
                )
            except create_collection_uc.CollectionNameTaken:
                form.add_error("name", "A collection with this name already exists.")
            except create_collection_uc.RecipeNotFound:
                form.add_error(None, "One of the selected recipes no longer exists.")
            else:
                return shortcuts.redirect("recipe-collection-detail", collection_id=result.collection_id)

        return shortcuts.render(request, "recipes/collection_form.html", {
            "mode": "create",
            "form": form,
            "form_action": urls.reverse("create-collection"),
            "name_value": request.POST.get("name", ""),
            "selected_recipes": recipe_queries.get_recipe_editor_options(recipe_ids=recipe_ids),
        })


class EditCollection(generic.View):
    """
    Edit an existing collection's name and ordered membership.

    :raises Http404: If no collection with the given id exists.
    """

    def get(self, request: http.HttpRequest, collection_id: int) -> http.HttpResponse:
        try:
            detail = recipe_queries.get_collection_detail(collection_id=collection_id)
        except recipe_queries.CollectionNotFound:
            raise http.Http404
        selected = recipe_queries.get_recipe_editor_options(
            recipe_ids=[member.recipe_id for member in detail.members]
        )
        return shortcuts.render(request, "recipes/collection_form.html", {
            "mode": "edit",
            "form": interface_forms.Collection(initial={"name": detail.name}),
            "form_action": urls.reverse("edit-collection", kwargs={"collection_id": collection_id}),
            "name_value": detail.name,
            "selected_recipes": selected,
            "collection_id": collection_id,
        })

    def post(self, request: http.HttpRequest, collection_id: int) -> http.HttpResponse:
        form = interface_forms.Collection(request.POST)
        recipe_ids = _recipe_ids_from_request(request)
        if recipe_ids is None:
            return http.HttpResponseBadRequest("recipe_ids must be integers")

        if form.is_valid():
            try:
                update_collection_uc.update_collection(
                    collection_id=collection_id,
                    name=form.cleaned_data["name"],
                    recipe_ids=recipe_ids,
                )
            except update_collection_uc.CollectionNotFound:
                raise http.Http404
            except update_collection_uc.CollectionNameTaken:
                form.add_error("name", "A collection with this name already exists.")
            except update_collection_uc.RecipeNotFound:
                form.add_error(None, "One of the selected recipes no longer exists.")
            else:
                return shortcuts.redirect("recipe-collection-detail", collection_id=collection_id)

        return shortcuts.render(request, "recipes/collection_form.html", {
            "mode": "edit",
            "form": form,
            "form_action": urls.reverse("edit-collection", kwargs={"collection_id": collection_id}),
            "name_value": request.POST.get("name", ""),
            "selected_recipes": recipe_queries.get_recipe_editor_options(recipe_ids=recipe_ids),
            "collection_id": collection_id,
        })


class DeleteCollection(generic.View):
    """
    Delete a collection, then return to the list.

    :raises Http404: If no collection with the given id exists.
    """

    def post(self, request: http.HttpRequest, collection_id: int) -> http.HttpResponse:
        try:
            delete_collection_uc.delete_collection(collection_id=collection_id)
        except delete_collection_uc.CollectionNotFound:
            raise http.Http404
        return shortcuts.redirect("recipes-collections")


class CollectionRecipeSearch(generic.View):
    """
    Return the recipe search results for the collection editor's add panel.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        name_search = request.GET.get("name_search", "").strip()
        options = recipe_queries.get_recipes_for_collection_editor(name_search=name_search)
        return shortcuts.render(
            request,
            "recipes/partials/collection_recipe_search_results.html",
            {"recipe_options": options},
        )
