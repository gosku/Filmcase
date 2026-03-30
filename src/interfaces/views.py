import mimetypes
import structlog
from pathlib import Path

from django.conf import settings
from django.core import paginator as django_paginator
from django.db import models as db_models
from django import http
from django import shortcuts
from django.views import generic
from django.views.decorators import http as http_decorators

from src.application.usecases.camera import get_camera_slots as get_camera_slots_uc
from src.application.usecases.camera import push_recipe as push_recipe_uc
from src.data import models
from src.domain.camera import ptp_device
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images.thumbnails import operations as thumbnail_operations
from src.domain.images.thumbnails import queries as thumbnail_queries


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


def _get_filtered_images(request) -> db_models.QuerySet:
    qs = models.Image.objects.select_related("fujifilm_recipe")
    recipe_ids = request.GET.getlist("recipe_id")
    if recipe_ids:
        qs = qs.filter(fujifilm_recipe_id__in=recipe_ids)
    for field, _ in filter_queries.RECIPE_FILTER_FIELDS:
        values = request.GET.getlist(field)
        if values:
            qs = qs.filter(**{f"fujifilm_recipe__{field}__in": values})
    if request.GET.get("favorites_first", "1") == "1":
        return qs.order_by("-is_favorite", "-taken_at")
    return qs.order_by("-taken_at")


def _get_recipe_options(request, active_field_filters: dict[str, list[str]]) -> dict:
    selected = request.GET.getlist("recipe_id")

    # Count images per recipe after applying active field filters.
    filtered_qs = models.Image.objects.filter(fujifilm_recipe__isnull=False)
    for field, values in active_field_filters.items():
        if values:
            filtered_qs = filtered_qs.filter(**{f"fujifilm_recipe__{field}__in": values})
    filtered_counts = {
        str(row["fujifilm_recipe_id"]): row["count"]
        for row in filtered_qs.values("fujifilm_recipe_id").annotate(count=db_models.Count("id"))
    }

    # Show notable recipes (>50 total images or named) plus any currently selected.
    selected_ids = [int(r) for r in selected if r.isdigit()]
    recipes = (
        models.FujifilmRecipe.objects.annotate(total_images=db_models.Count("images"))
        .filter(db_models.Q(total_images__gt=50) | ~db_models.Q(name="") | db_models.Q(id__in=selected_ids))
        .order_by("-total_images")
    )

    options = []
    for recipe in recipes:
        count = filtered_counts.get(str(recipe.id), 0)
        name = recipe.name if recipe.name else f"{recipe.id} - {recipe.film_simulation}"
        options.append({
            "value": str(recipe.id),
            "label": f"{name} ({count})",
            "available": count > 0,
            "selected": str(recipe.id) in selected,
        })
    # Available recipes first; stable sort preserves total_images order within each group.
    options.sort(key=lambda o: 0 if o["available"] else 1)

    return {"label": "Recipe", "options": options, "selected": selected}


def _paginate(request, qs) -> django_paginator.Page:
    paginator = django_paginator.Paginator(qs, settings.GALLERY_PAGE_SIZE)
    page_number = request.GET.get("page", 1)
    return paginator.get_page(page_number)


def gallery_view(request):
    active_filters = _active_filters_from_request(request)
    active_field_filters = {k: v for k, v in active_filters.items() if k != "recipe_id"}
    page_obj = _paginate(request, _get_filtered_images(request))
    sidebar_options = filter_queries.get_sidebar_filter_options(active_filters)
    recipe_options = _get_recipe_options(request, active_field_filters)
    if request.headers.get("HX-Request"):
        return shortcuts.render(request, "images/_gallery_htmx_filter_response.html", {
            "page_obj": page_obj,
            "sidebar_options": sidebar_options,
            "recipe_options": recipe_options,
        })
    favorites_first = request.GET.get("favorites_first", "1")
    return shortcuts.render(
        request,
        "images/gallery.html",
        {
            "page_obj": page_obj,
            "sidebar_options": sidebar_options,
            "recipe_options": recipe_options,
            "favorites_first": favorites_first,
        },
    )


def image_detail_view(request, image_id):
    image = shortcuts.get_object_or_404(
        models.Image.objects.select_related("fujifilm_recipe", "fujifilm_exif"),
        pk=image_id,
    )
    if request.headers.get("HX-Request"):
        ids = list(_get_filtered_images(request).values_list("id", flat=True))
        try:
            idx = ids.index(image_id)
        except ValueError:
            idx = -1
        context = {
            "image": image,
            "prev_id": ids[idx - 1] if idx > 0 else None,
            "next_id": ids[idx + 1] if idx < len(ids) - 1 else None,
        }
        return shortcuts.render(request, "images/_image_detail_partial.html", context)
    return shortcuts.render(request, "images/image_detail.html", {"image": image})


def gallery_results_view(request):
    page_obj = _paginate(request, _get_filtered_images(request))
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
def toggle_favorite_view(request, image_id):
    shortcuts.get_object_or_404(models.Image, pk=image_id)
    is_favorite = image_operations.toggle_image_favorite(image_id=image_id)
    return shortcuts.render(
        request,
        "images/_favorite_button.html",
        {"image_id": image_id, "is_favorite": is_favorite},
    )


_SLOT_TO_INDEX = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5, "C6": 6, "C7": 7}


class SelectSlotView(generic.View):
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
            structlog.get_logger().exception("Unexpected error in SelectSlotView.get")
            if is_htmx:
                return shortcuts.render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": "Unexpected error happened"})
            return http.JsonResponse({"error": "Unexpected error happened"}, status=500)
        slots = [{"label": f"C{s.index}", "name": s.name, "film_sim": s.film_sim_name} for s in states]
        template = "recipes/_select_slot_partial.html" if is_htmx else "recipes/select_slot.html"
        return shortcuts.render(request, template, {"recipe": self.recipe, "slots": slots})


class PushRecipeToCameraView(generic.View):
    def dispatch(self, request, *args, **kwargs):
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        slot_index = _SLOT_TO_INDEX.get(kwargs["slot"])
        if slot_index is None:
            raise http.Http404
        self.slot_index = slot_index
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, recipe_id, slot):
        is_htmx = request.headers.get("HX-Request")
        recipe_data = image_queries.recipe_from_db(recipe=self.recipe)
        error_ctx = {"recipe_id": recipe_id, "slot": slot}
        try:
            push_recipe_uc.push_recipe_to_camera(recipe_data, slot_index=self.slot_index)
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
            structlog.get_logger().exception("Unexpected error in PushRecipeToCameraView.post")
            error = "An unexpected error occurred. Please try again."
            if is_htmx:
                return shortcuts.render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return http.JsonResponse({"error": error}, status=500)
        if is_htmx:
            return shortcuts.render(request, "recipes/_push_result_partial.html", {"success": True, "message": f"Recipe saved to {slot}"})
        return http.JsonResponse({"message": f"Recipe saved in {slot}"})


class SetRecipeNameView(generic.View):
    def dispatch(self, request, *args, **kwargs):
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, recipe_id):
        name = request.POST.get("name", "").strip()
        try:
            image_operations.set_recipe_name(recipe=self.recipe, name=name)
        except image_operations.RecipeNameValidationError:
            return shortcuts.render(request, "recipes/_recipe_name_prompt.html", {
                "recipe": self.recipe,
                "error": "Name must be 25 ASCII characters max.",
                "show_form": True,
                "submitted_name": name,
            })
        except Exception:
            structlog.get_logger().exception("Unexpected error in SetRecipeNameView.post")
            return shortcuts.render(request, "recipes/_recipe_name_prompt.html", {
                "recipe": self.recipe,
                "error": "Something unexpected happened.",
                "show_form": True,
                "submitted_name": name,
            })
        return shortcuts.render(request, "recipes/_recipe_name_row.html", {"recipe": self.recipe})


def _resized_image_response(path: Path, width: int):
    cache_path = thumbnail_operations.generate_thumbnail(original_path=path, width=width)
    response = http.FileResponse(cache_path.open("rb"), content_type=thumbnail_queries.thumbnail_content_type(cache_path=cache_path))
    response["Cache-Control"] = "max-age=86400"
    return response
