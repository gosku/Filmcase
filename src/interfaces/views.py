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
from src.data import models
from src.domain.camera import ptp_device
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images.thumbnails import operations as thumbnail_operations


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
    favorites_first = request.GET.get("favorites_first", "1") == "1"
    gallery = filter_queries.get_gallery_data(
        active_filters=active_filters,
        favorites_first=favorites_first,
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
            "favorites_first": "1" if favorites_first else "0",
        },
    )


def image_detail_view(request, image_id):
    if request.headers.get("HX-Request"):
        active_filters = _active_filters_from_request(request)
        favorites_first = request.GET.get("favorites_first", "1") == "1"
        try:
            detail = image_queries.get_image_detail(
                image_id=image_id,
                active_filters=active_filters,
                favorites_first=favorites_first,
            )
        except models.Image.DoesNotExist:
            raise http.Http404
        return shortcuts.render(request, "images/_image_detail_partial.html", {
            "image": detail.image,
            "prev_id": detail.prev_id,
            "next_id": detail.next_id,
        })
    image = shortcuts.get_object_or_404(
        models.Image.objects.select_related("fujifilm_recipe", "fujifilm_exif"),
        pk=image_id,
    )
    return shortcuts.render(request, "images/image_detail.html", {"image": image})


def gallery_results_view(request):
    active_filters = _active_filters_from_request(request)
    favorites_first = request.GET.get("favorites_first", "1") == "1"
    qs = filter_queries.get_filtered_images(active_filters=active_filters, favorites_first=favorites_first)
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
def toggle_favorite_view(request, image_id):
    try:
        is_favorite = image_operations.toggle_image_favorite(image_id=image_id)
    except models.Image.DoesNotExist:
        raise http.Http404
    return shortcuts.render(
        request,
        "images/_favorite_button.html",
        {"image_id": image_id, "is_favorite": is_favorite},
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
            image_operations.set_recipe_name(recipe=self.recipe, name=name)
        except image_operations.RecipeNameValidationError:
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


def _resized_image_response(path: Path, width: int):
    cache_path, content_type = thumbnail_operations.generate_thumbnail_with_content_type(original_path=path, width=width)
    response = http.FileResponse(cache_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "max-age=86400"
    return response
