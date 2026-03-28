import logging
import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from django.views.decorators.http import require_POST

from src.application.usecases.camera.get_camera_slots import get_camera_slots
from src.application.usecases.camera.push_recipe import RecipeWriteError, push_recipe_to_camera
from src.data.models import FujifilmRecipe, Image
from src.domain.camera.ptp_device import CameraConnectionError, CameraWriteError
from src.domain.images.operations import toggle_image_favorite
from src.domain.images.queries import recipe_from_db
from src.domain.images.thumbnails.operations import generate_thumbnail
from src.domain.images.thumbnails.queries import thumbnail_content_type

RECIPE_FILTER_FIELDS = [
    ("film_simulation", "Film Simulation"),
    ("dynamic_range", "Dynamic Range"),
    ("d_range_priority", "D-Range Priority"),
    ("grain_roughness", "Grain Roughness"),
    ("grain_size", "Grain Size"),
    ("color_chrome_effect", "Color Chrome Effect"),
    ("color_chrome_fx_blue", "Color Chrome FX Blue"),
    ("white_balance", "White Balance"),
]


def _get_filtered_images(request):
    qs = Image.objects.select_related("fujifilm_recipe")
    recipe_id = request.GET.get("recipe_id")
    if recipe_id:
        qs = qs.filter(fujifilm_recipe_id=recipe_id)
    for field, _ in RECIPE_FILTER_FIELDS:
        value = request.GET.get(field)
        if value:
            qs = qs.filter(**{f"fujifilm_recipe__{field}": value})
    if request.GET.get("favorites_first", "1") == "1":
        return qs.order_by("-is_favorite", "-taken_at")
    return qs.order_by("-taken_at")


def _get_recipe_options(request):
    recipes = (
        FujifilmRecipe.objects.annotate(image_count=Count("images"))
        .filter(Q(image_count__gt=50) | ~Q(name=""))
        .order_by("-image_count")
    )
    selected = request.GET.get("recipe_id", "")
    options = [
        {
            "value": str(recipe.id),
            "label": f"{recipe.name if recipe.name else f'{recipe.id} - {recipe.film_simulation}'} ({recipe.image_count})",
        }
        for recipe in recipes
    ]
    return {"label": "Recipe", "options": options, "selected": selected}


def _paginate(request, qs):
    paginator = Paginator(qs, settings.GALLERY_PAGE_SIZE)
    page_number = request.GET.get("page", 1)
    return paginator.get_page(page_number)


def _get_sidebar_options(request):
    options = {}
    for field, label in RECIPE_FILTER_FIELDS:
        values = (
            FujifilmRecipe.objects.values_list(field, flat=True)
            .distinct()
            .exclude(**{field: ""})
            .order_by(field)
        )
        options[field] = {
            "label": label,
            "values": list(values),
            "selected": request.GET.get(field, ""),
        }
    return options


def gallery_view(request):
    page_obj = _paginate(request, _get_filtered_images(request))
    if request.headers.get("HX-Request"):
        return render(request, "images/_gallery_htmx_filter_response.html", {"page_obj": page_obj})
    sidebar_options = _get_sidebar_options(request)
    recipe_options = _get_recipe_options(request)
    favorites_first = request.GET.get("favorites_first", "1")
    return render(
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
    image = get_object_or_404(
        Image.objects.select_related("fujifilm_recipe", "fujifilm_exif"),
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
        return render(request, "images/_image_detail_partial.html", context)
    return render(request, "images/image_detail.html", {"image": image})


def gallery_results_view(request):
    page_obj = _paginate(request, _get_filtered_images(request))
    return render(request, "images/_gallery_htmx_scroll_response.html", {"page_obj": page_obj})


def image_file_view(request, image_id):
    image = get_object_or_404(Image, pk=image_id)
    path = Path(image.filepath)
    if not path.is_file():
        raise Http404
    width_param = request.GET.get("width")
    if width_param:
        try:
            width = int(width_param)
        except ValueError:
            raise Http404
        return _resized_image_response(path, width)
    content_type, _ = mimetypes.guess_type(image.filepath)
    return FileResponse(path.open("rb"), content_type=content_type or "image/jpeg")


@require_POST
def toggle_favorite_view(request, image_id):
    get_object_or_404(Image, pk=image_id)
    is_favorite = toggle_image_favorite(image_id=image_id)
    return render(
        request,
        "images/_favorite_button.html",
        {"image_id": image_id, "is_favorite": is_favorite},
    )


_SLOT_TO_INDEX = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5, "C6": 6, "C7": 7}


class SelectSlotView(View):
    def dispatch(self, request, *args, **kwargs):
        recipe = get_object_or_404(FujifilmRecipe, pk=kwargs["recipe_id"])
        if not recipe.name:
            raise Http404
        self.recipe = recipe
        return super().dispatch(request, *args, **kwargs)

    def get(self, request, recipe_id):
        is_htmx = request.headers.get("HX-Request")
        try:
            states = get_camera_slots()
        except CameraConnectionError as e:
            if is_htmx:
                return render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": f"Camera connection error: {e}"})
            return JsonResponse({"error": f"Camera connection error: {e}"}, status=503)
        except CameraWriteError as e:
            if is_htmx:
                return render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": f"Camera write error: {e}"})
            return JsonResponse({"error": f"Camera write error: {e}"}, status=500)
        except Exception:
            logging.exception("Unexpected error in SelectSlotView.get")
            if is_htmx:
                return render(request, "recipes/_select_slot_partial.html", {"recipe": self.recipe, "slots": [], "error": "Unexpected error happened"})
            return JsonResponse({"error": "Unexpected error happened"}, status=500)
        slots = [{"label": f"C{s.index}", "name": s.name, "film_sim": s.film_sim_name} for s in states]
        template = "recipes/_select_slot_partial.html" if is_htmx else "recipes/select_slot.html"
        return render(request, template, {"recipe": self.recipe, "slots": slots})


class PushRecipeToCameraView(View):
    def dispatch(self, request, *args, **kwargs):
        self.recipe = get_object_or_404(FujifilmRecipe, pk=kwargs["recipe_id"])
        slot_index = _SLOT_TO_INDEX.get(kwargs["slot"])
        if slot_index is None:
            raise Http404
        self.slot_index = slot_index
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, recipe_id, slot):
        is_htmx = request.headers.get("HX-Request")
        recipe_data = recipe_from_db(recipe=self.recipe)
        error_ctx = {"recipe_id": recipe_id, "slot": slot}
        try:
            push_recipe_to_camera(recipe_data, slot_index=self.slot_index)
        except RecipeWriteError as e:
            error = f"Some settings couldn't be saved ({', '.join(e.failed_properties)}). Please try again."
            if is_htmx:
                return render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return JsonResponse({"error": error}, status=500)
        except CameraConnectionError:
            error = "No camera found. Make sure it's connected via USB and set to PC Connection or RAW CONV. mode."
            if is_htmx:
                return render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return JsonResponse({"error": error}, status=503)
        except CameraWriteError:
            error = "The camera rejected a write operation. Please try again."
            if is_htmx:
                return render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return JsonResponse({"error": error}, status=500)
        except Exception:
            logging.exception("Unexpected error in PushRecipeToCameraView.post")
            error = "An unexpected error occurred. Please try again."
            if is_htmx:
                return render(request, "recipes/_push_result_partial.html", {"error": error, **error_ctx})
            return JsonResponse({"error": error}, status=500)
        if is_htmx:
            return render(request, "recipes/_push_result_partial.html", {"success": True, "message": f"Recipe saved to {slot}"})
        return JsonResponse({"message": f"Recipe saved in {slot}"})


def _resized_image_response(path: Path, width: int):
    cache_path = generate_thumbnail(original_path=path, width=width)
    response = FileResponse(cache_path.open("rb"), content_type=thumbnail_content_type(cache_path=cache_path))
    response["Cache-Control"] = "max-age=86400"
    return response
