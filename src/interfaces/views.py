import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from src.data.models import FujifilmRecipe, Image
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
    return qs.order_by("-is_favorite", "-taken_at")


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
    sidebar_options = _get_sidebar_options(request)
    recipe_options = _get_recipe_options(request)
    return render(
        request,
        "images/gallery.html",
        {"page_obj": page_obj, "sidebar_options": sidebar_options, "recipe_options": recipe_options},
    )


def gallery_results_view(request):
    page_obj = _paginate(request, _get_filtered_images(request))
    return render(request, "images/_gallery_results.html", {"page_obj": page_obj})


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


def _resized_image_response(path: Path, width: int):
    cache_path = generate_thumbnail(original_path=path, width=width)
    response = FileResponse(cache_path.open("rb"), content_type=thumbnail_content_type(cache_path=cache_path))
    response["Cache-Control"] = "max-age=86400"
    return response
