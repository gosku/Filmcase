import mimetypes
from pathlib import Path

from django.conf import settings
from django import http
from django import shortcuts
from django.views.decorators import http as http_decorators

from src.data import models
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images.thumbnails import operations as thumbnail_operations


def _active_filters_from_request(request: http.HttpRequest) -> dict[str, list[str]]:
    filters = {
        field: request.GET.getlist(field)
        for field, _ in filter_queries.RECIPE_FILTER_FIELDS
        if request.GET.getlist(field)
    }
    recipe_ids = request.GET.getlist("recipe_id")
    if recipe_ids:
        filters["recipe_id"] = recipe_ids
    sensor_values = request.GET.getlist("sensors")
    if sensor_values:
        filters["sensors"] = sensor_values
    return filters


def gallery_view(request: http.HttpRequest) -> http.HttpResponse:
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


def image_detail_view(request: http.HttpRequest, image_id: int) -> http.HttpResponse:
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
    return shortcuts.render(request, "images/image_detail.html", {
        "image": detail.image,
        "prev_id": detail.prev_id,
        "next_id": detail.next_id,
        "max_rating": max_rating,
        "rating_range": rating_range,
    })


def gallery_results_view(request: http.HttpRequest) -> http.HttpResponse:
    active_filters = _active_filters_from_request(request)
    rating_first = request.GET.get("rating_first", "1") == "1"
    qs = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    from django.core import paginator as django_paginator
    page_obj = django_paginator.Paginator(qs, settings.GALLERY_PAGE_SIZE).get_page(request.GET.get("page", 1))
    return shortcuts.render(request, "images/_gallery_htmx_scroll_response.html", {"page_obj": page_obj})


def image_file_view(request: http.HttpRequest, image_id: int) -> http.HttpResponseBase:
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
def set_image_rating_view(request: http.HttpRequest, image_id: int) -> http.HttpResponse:
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


def _resized_image_response(path: Path, width: int) -> http.FileResponse:
    cache_path, content_type = thumbnail_operations.generate_thumbnail_with_content_type(original_path=path, width=width)
    response = http.FileResponse(cache_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "max-age=86400"
    return response
