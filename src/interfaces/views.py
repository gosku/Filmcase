import json
import mimetypes
import structlog
from pathlib import Path

from django.conf import settings
from django.core import paginator as django_paginator
from django import http
from django import shortcuts
from django.views import generic
from django.views.decorators import http as http_decorators

from src.application.usecases.camera import get_camera_slots as get_camera_slots_uc
from src.application.usecases.camera import push_recipe as push_recipe_uc
from src.application.usecases.recipes import build_graph as build_graph_uc
from src.application.usecases.recipes import import_recipes_from_uploaded_files as import_recipes_uc
from src.data import models
from src.domain.camera import ptp_device
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images.thumbnails import operations as thumbnail_operations
from src.domain.recipes import graph as recipe_graph
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import queries as recipe_queries


def _active_filters_from_request(request) -> dict[str, list[str]]:
    filters = {
        field: request.GET.getlist(field)
        for field, _ in filter_queries.RECIPE_FILTER_FIELDS
        if request.GET.getlist(field)
    }
    recipe_ids = request.GET.getlist("recipe_id")
    if recipe_ids:
        filters["recipe_id"] = recipe_ids
    return filters


def gallery_view(request):
    active_filters = _active_filters_from_request(request)
    rating_first = request.GET.get("rating_first", "1") == "1"
    gallery = filter_queries.get_gallery_data(
        active_filters=active_filters,
        rating_first=rating_first,
        page_number=request.GET.get("page", 1),
        page_size=settings.GALLERY_PAGE_SIZE,
    )
    if request.headers.get("HX-Request"):
        return shortcuts.render(request, "images/_gallery_htmx_filter_response.html", {
            "page_obj": gallery.page_obj,
            "sidebar_options": gallery.sidebar_options,
            "recipe_options": gallery.recipe_options,
        })
    return shortcuts.render(
        request,
        "images/gallery.html",
        {
            "page_obj": gallery.page_obj,
            "sidebar_options": gallery.sidebar_options,
            "recipe_options": gallery.recipe_options,
            "rating_first": "1" if rating_first else "0",
        },
    )


def image_detail_view(request, image_id):
    max_rating = settings.IMAGE_MAX_RATING
    rating_range = range(1, max_rating + 1)
    if request.headers.get("HX-Request"):
        active_filters = _active_filters_from_request(request)
        rating_first = request.GET.get("rating_first", "1") == "1"
        try:
            detail = image_queries.get_image_detail(
                image_id=image_id,
                active_filters=active_filters,
                rating_first=rating_first,
            )
        except models.Image.DoesNotExist:
            raise http.Http404
        return shortcuts.render(request, "images/_image_detail_partial.html", {
            "image": detail.image,
            "prev_id": detail.prev_id,
            "next_id": detail.next_id,
            "max_rating": max_rating,
            "rating_range": rating_range,
        })
    image = shortcuts.get_object_or_404(
        models.Image.objects.select_related("fujifilm_recipe", "fujifilm_exif"),
        pk=image_id,
    )
    return shortcuts.render(request, "images/image_detail.html", {
        "image": image,
        "max_rating": max_rating,
        "rating_range": rating_range,
    })


def gallery_results_view(request):
    active_filters = _active_filters_from_request(request)
    rating_first = request.GET.get("rating_first", "1") == "1"
    qs = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    page_obj = django_paginator.Paginator(qs, settings.GALLERY_PAGE_SIZE).get_page(request.GET.get("page", 1))
    return shortcuts.render(request, "images/_gallery_htmx_scroll_response.html", {"page_obj": page_obj})


def image_file_view(request, image_id):
    image = shortcuts.get_object_or_404(models.Image, pk=image_id)
    path = Path(image.filepath)
    if not path.is_file():
        raise http.Http404
    width_param = request.GET.get("width")
    if width_param:
        try:
            width = int(width_param)
        except ValueError:
            raise http.Http404
        return _resized_image_response(path, width)
    content_type, _ = mimetypes.guess_type(image.filepath)
    return http.FileResponse(path.open("rb"), content_type=content_type or "image/jpeg")


@http_decorators.require_POST
def set_image_rating_view(request, image_id):
    try:
        image = models.Image.objects.get(pk=image_id)
    except models.Image.DoesNotExist:
        raise http.Http404
    try:
        rating = int(request.POST.get("rating", 0))
    except (ValueError, TypeError):
        raise http.Http404
    try:
        image_operations.set_image_rating(image=image, rating=rating)
    except image_operations.InvalidImageRatingError:
        raise http.Http404
    max_rating = settings.IMAGE_MAX_RATING
    return shortcuts.render(
        request,
        "images/_rating_widget.html",
        {
            "image_id": image_id,
            "rating": image.rating,
            "max_rating": max_rating,
            "rating_range": range(1, max_rating + 1),
        },
    )


_NOTABLE_RECIPE_MIN_IMAGES = 50  # recipes with fewer images are hidden unless named or selected
_SLOT_TO_INDEX = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5, "C6": 6, "C7": 7}


class SelectSlot(generic.View):
    def dispatch(self, request, *args, **kwargs):
        recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        if not recipe.name:
            raise http.Http404
        self.recipe = recipe
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, recipe_id):
        is_htmx = request.headers.get("HX-Request")
        try:
            states = get_camera_slots_uc.get_camera_slots()
        except ptp_device.CameraConnectionError as e:
            if is_htmx:
                return shortcuts.render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": f"Camera connection error: {e}"})
            return http.JsonResponse({"error": f"Camera connection error: {e}"}, status=503)
        except ptp_device.CameraWriteError as e:
            if is_htmx:
                return shortcuts.render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": f"Camera write error: {e}"})
            return http.JsonResponse({"error": f"Camera write error: {e}"}, status=500)
        except Exception:
            structlog.get_logger().exception("Unexpected error in SelectSlot.get")
            if is_htmx:
                return shortcuts.render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": "Unexpected error happened"})
            return http.JsonResponse({"error": "Unexpected error happened"}, status=500)
        slots = [{"label": f"C{s.index}", "name": s.name, "film_sim": s.film_sim_name} for s in states]
        template = "recipes/_select_slot_partial.html" if is_htmx else "recipes/select_slot.html"
        return shortcuts.render(request, template, {"recipe": self.recipe, "slots": slots})


class PushRecipeToCamera(generic.View):
    def dispatch(self, request, *args, **kwargs):
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        slot_index = _SLOT_TO_INDEX.get(kwargs["slot"])
        if slot_index is None:
            raise http.Http404
        self.slot_index = slot_index
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, recipe_id, slot):
        is_htmx = request.headers.get("HX-Request")
        error_ctx = {"recipe_id": recipe_id, "slot": slot}
        try:
            push_recipe_uc.push_recipe_to_camera(self.recipe, slot_index=self.slot_index)
        except push_recipe_uc.RecipeWriteError as e:
            error = f"Some settings couldn't be saved ({', '.join(e.failed_properties)}). Please try again."
            if is_htmx:
                return shortcuts.render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return http.JsonResponse({"error": error}, status=500)
        except ptp_device.CameraConnectionError:
            error = "No camera found. Make sure it's connected via USB and set to PC Connection or RAW CONV. mode."
            if is_htmx:
                return shortcuts.render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return http.JsonResponse({"error": error}, status=503)
        except ptp_device.CameraWriteError:
            error = "The camera rejected a write operation. Please try again."
            if is_htmx:
                return shortcuts.render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return http.JsonResponse({"error": error}, status=500)
        except Exception:
            structlog.get_logger().exception("Unexpected error in PushRecipeToCamera.post")
            error = "An unexpected error occurred. Please try again."
            if is_htmx:
                return shortcuts.render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return http.JsonResponse({"error": error}, status=500)
        if is_htmx:
            return shortcuts.render(request, "recipes/_push_result_partial.html", {"success": True, "message": f"Recipe saved to {slot}"})
        return http.JsonResponse({"message": f"Recipe saved in {slot}"})


class SetRecipeName(generic.View):
    def dispatch(self, request, *args, **kwargs):
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, recipe_id):
        name = request.POST.get("name", "").strip()
        try:
            recipe_operations.set_recipe_name(recipe=self.recipe, name=name)
        except recipe_operations.RecipeNameValidationError:
            return shortcuts.render(request, "recipes/_recipe_name_prompt.html", {
                "recipe": self.recipe,
                "error": "Name must be 25 ASCII characters max.",
                "show_form": True,
                "submitted_name": name,
            })
        except Exception:
            structlog.get_logger().exception("Unexpected error in SetRecipeName.post")
            return shortcuts.render(request, "recipes/_recipe_name_prompt.html", {
                "recipe": self.recipe,
                "error": "Something unexpected happened.",
                "show_form": True,
                "submitted_name": name,
            })
        return shortcuts.render(request, "recipes/_recipe_name_row.html", {"recipe": self.recipe})


def _recipe_explorer_filters_from_request(request: http.HttpRequest) -> dict[str, list[str]]:
    return {
        field: request.GET.getlist(field)
        for field, _ in filter_queries.RECIPE_FILTER_FIELDS
        if request.GET.getlist(field)
    }


def recipes_explorer_view(request: http.HttpRequest) -> http.HttpResponse:
    active_filters = _recipe_explorer_filters_from_request(request)
    name_search = request.GET.get("name_search", "").strip()
    gallery = recipe_queries.get_recipe_gallery_data(
        active_filters=active_filters,
        name_search=name_search,
        page_number=request.GET.get("page", 1),
        page_size=settings.RECIPE_EXPLORER_PAGE_SIZE,
    )
    ctx = {"page_obj": gallery.page_obj, "sidebar_options": gallery.sidebar_options, "name_search": name_search}
    if request.headers.get("HX-Request"):
        return shortcuts.render(request, "recipes/partials/htmx_filter_response.html", ctx)
    return shortcuts.render(request, "recipes/recipes_explorer.html", ctx)


def recipes_explorer_results_view(request: http.HttpRequest) -> http.HttpResponse:
    active_filters = _recipe_explorer_filters_from_request(request)
    name_search = request.GET.get("name_search", "").strip()
    gallery = recipe_queries.get_recipe_gallery_data(
        active_filters=active_filters,
        name_search=name_search,
        page_number=request.GET.get("page", 1),
        page_size=settings.RECIPE_EXPLORER_PAGE_SIZE,
    )
    return shortcuts.render(request, "recipes/partials/htmx_scroll_response.html", {"page_obj": gallery.page_obj})


def recipe_detail_view(request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
    try:
        detail = recipe_queries.get_recipe_detail(recipe_id=recipe_id)
    except models.FujifilmRecipe.DoesNotExist:
        raise http.Http404
    ctx = {"recipe": detail.recipe, "is_monochromatic": detail.is_monochromatic}
    if request.headers.get("HX-Request"):
        return shortcuts.render(request, "recipes/partials/recipe_detail.html", ctx)
    return shortcuts.render(request, "recipes/recipe_detail.html", ctx)


_RECIPES_GRAPH_DEFAULT_FILM_SIM = "Provia"


def _root_fields_json(root_id: int | None) -> list[dict[str, str]]:
    if root_id is None:
        return []
    try:
        root = models.FujifilmRecipe.objects.get(pk=root_id)
    except models.FujifilmRecipe.DoesNotExist:
        return []
    return [{"field": f.field, "value": f.value} for f in recipe_queries.get_recipe_all_fields(recipe=root)]


def recipes_graph_view(request: http.HttpRequest) -> http.HttpResponse:
    film_simulation = request.GET.get("film_sim", _RECIPES_GRAPH_DEFAULT_FILM_SIM)
    result = build_graph_uc.build_recipe_network(film_simulation=film_simulation)
    root_id = result.graph_data.root_id
    cyto_elements = [
        {
            "data": {
                "id": str(n.id),
                "label": n.label,
                "distance": n.distance,
                "image_count": n.image_count,
                "is_root": n.id == root_id,
            }
        }
        for n in result.graph_data.nodes
    ] + [
        {
            "data": {
                "source": str(e.source),
                "target": str(e.target),
                "distance": e.distance,
                "distanceLabel": f"d={e.distance}" if e.distance > 1 else "",
            }
        }
        for e in result.graph_data.edges
    ]
    root_fields = _root_fields_json(root_id)
    root_label = ""
    if root_id is not None:
        root_node = next((n for n in result.graph_data.nodes if n.id == root_id), None)
        root_label = root_node.label if root_node else ""
    if request.headers.get("Accept") == "application/json":
        return http.JsonResponse({
            "elements": cyto_elements,
            "root_id": root_id,
            "root_fields": root_fields,
            "root_label": root_label,
        })
    return shortcuts.render(request, "recipes/recipes_graph.html", {
        "graph_elements_json": json.dumps(cyto_elements),
        "root_id": root_id,
        "film_simulations": result.film_simulations,
        "active_film_simulation": result.active_film_simulation,
        "root_fields_json": json.dumps(root_fields),
        "root_label": root_label,
    })


def recipe_graph_view(request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
    root = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=recipe_id)
    all_recipes = list(models.FujifilmRecipe.objects.all())
    max_distance: int = settings.RECIPE_GRAPH_MAX_DISTANCE
    image_counts = recipe_queries.get_image_counts(recipe_pks=[r.pk for r in all_recipes])
    graph_data = recipe_graph.build_recipe_graph(
        root=root,
        all_recipes=all_recipes,
        max_distance=max_distance,
        image_counts=image_counts,
    )
    cyto_elements = [
        {
            "data": {
                "id": str(n.id),
                "label": n.label,
                "distance": n.distance,
                "image_count": n.image_count,
            }
        }
        for n in graph_data.nodes
    ] + [
        {
            "data": {
                "source": str(e.source),
                "target": str(e.target),
                "distance": e.distance,
                "distanceLabel": f"d={e.distance}" if e.distance > 1 else "",
            }
        }
        for e in graph_data.edges
    ]
    root_fields = [{"field": f.field, "value": f.value} for f in recipe_queries.get_recipe_all_fields(recipe=root)]
    root_label = root.name or f"#{root.pk}"
    if request.headers.get("Accept") == "application/json":
        return http.JsonResponse({
            "root_id": graph_data.root_id,
            "root_label": root_label,
            "root_fields": root_fields,
            "elements": cyto_elements,
        })
    return shortcuts.render(request, "recipes/recipe_graph.html", {
        "root_id": graph_data.root_id,
        "graph_elements_json": json.dumps(cyto_elements),
        "max_distance": max_distance,
        "root_fields_json": json.dumps(root_fields),
        "root_label": root_label,
    })


def recipe_images_view(request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
    """Return thumbnail URLs for all images belonging to a recipe.

    Images are ordered by rating descending, then taken_at descending.
    Response: JSON ``{"images": [{"id": int, "thumbnail_url": str}]}``.
    """
    shortcuts.get_object_or_404(models.FujifilmRecipe, pk=recipe_id)
    image_ids = image_queries.get_images_for_recipe(recipe_id=recipe_id)
    images = [
        {
            "id": image_id,
            "thumbnail_url": request.build_absolute_uri(
                f"/images/file/{image_id}/?width=600"
            ),
        }
        for image_id in image_ids
    ]
    return http.JsonResponse({"images": images})


def recipe_compare_image_view(request: http.HttpRequest, recipe_id: int, image_id: int) -> http.HttpResponse:
    """Return image URLs and prev/next IDs for one image within a recipe sequence.

    Response: JSON ``{"id": int, "thumbnail_url": str, "full_url": str, "prev_id": int|null, "next_id": int|null}``.
    """
    shortcuts.get_object_or_404(models.FujifilmRecipe, pk=recipe_id)
    try:
        page = image_queries.get_recipe_image_page(recipe_id=recipe_id, image_id=image_id)
    except models.Image.DoesNotExist:
        raise http.Http404
    return http.JsonResponse({
        "id": page.image_id,
        "thumbnail_url": request.build_absolute_uri(f"/images/file/{image_id}/?width=600"),
        "full_url": request.build_absolute_uri(f"/images/file/{image_id}/"),
        "prev_id": page.prev_id,
        "next_id": page.next_id,
    })


@http_decorators.require_POST
def import_recipes_from_uploaded_files_view(request: http.HttpRequest) -> http.HttpResponse:
    uploaded = request.FILES.getlist("images")
    if not uploaded:
        return shortcuts.render(
            request,
            "recipes/partials/_import_result.html",
            {"error": "No files were uploaded."},
        )

    files = [
        import_recipes_uc.UploadedFile(name=f.name, content=f.read())
        for f in uploaded
    ]

    try:
        result = import_recipes_uc.import_recipes_from_uploaded_files(files=files)
    except Exception:
        structlog.get_logger().exception("Unexpected error in import_recipes_from_uploaded_files_view")
        return shortcuts.render(
            request,
            "recipes/partials/_import_result.html",
            {"error": "An unexpected error occurred. Please try again."},
        )

    return shortcuts.render(
        request,
        "recipes/partials/_import_result.html",
        {"imported": result.imported, "failed": result.failed},
    )


def recipe_path_deltas_view(request: http.HttpRequest) -> http.HttpResponse:
    """Return per-node field deltas for an ordered path of recipe IDs.

    Accepts GET ?ids=1,2,3 where IDs are ordered root → clicked node.
    Returns JSON with root_diffs (root vs clicked) and path_nodes (per-step diffs).
    """
    ids_param = request.GET.get("ids", "")
    try:
        path_ids = [int(x) for x in ids_param.split(",") if x.strip()]
    except ValueError:
        return http.HttpResponseBadRequest("ids must be comma-separated integers")
    if not path_ids:
        return http.HttpResponseBadRequest("ids parameter is required")
    result = recipe_queries.get_path_deltas(path_ids=path_ids)
    def _serialize_field(f: recipe_queries.FieldValue) -> dict[str, str | None]:
        return {"field": f.field, "value": f.value, "before": f.before}

    return http.JsonResponse({
        "root_diffs": [_serialize_field(f) for f in result.root_diffs],
        "path_nodes": [
            {
                "id": n.recipe_id,
                "label": n.label,
                "fields": [_serialize_field(f) for f in n.changed_fields],
            }
            for n in result.path_nodes
        ],
    })


def _resized_image_response(path: Path, width: int):
    cache_path, content_type = thumbnail_operations.generate_thumbnail_with_content_type(original_path=path, width=width)
    response = http.FileResponse(cache_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "max-age=86400"
    return response
