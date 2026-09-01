import mimetypes
from pathlib import Path

import structlog
from django.core import paginator as django_paginator
from django import http
from django import shortcuts
from django.views import generic

from src.application.usecases.images import remove_images as remove_images_uc
from src.application.usecases.images import set_images_rating as set_images_rating_uc
from src.data import models
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.settings import queries as settings_queries
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


class Gallery(generic.View):
    """
    Display the image gallery with filtering and pagination.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        active_filters = _active_filters_from_request(request)
        rating_first = request.GET.get("rating_first", "1") == "1"
        gallery = filter_queries.get_gallery_data(
            active_filters=active_filters,
            rating_first=rating_first,
            page_number=request.GET.get("page", 1),
            page_size=settings_queries.get_gallery_page_size(),
        )
        if request.headers.get("HX-Request"):
            return shortcuts.render(request, "images/_gallery_htmx_filter_response.html", {
                "page_obj": gallery.page_obj,
                "sidebar_options": gallery.sidebar_options,
                "recipe_options": gallery.recipe_options,
            })
        max_rating = settings_queries.get_image_max_rating()
        return shortcuts.render(
            request,
            "images/gallery.html",
            {
                "page_obj": gallery.page_obj,
                "sidebar_options": gallery.sidebar_options,
                "recipe_options": gallery.recipe_options,
                "rating_first": "1" if rating_first else "0",
                "max_rating": max_rating,
                "rating_range": range(1, max_rating + 1),
            },
        )


class ImageDetail(generic.View):
    """
    Display the detail view of a single image.

    :raises Http404: if no image with the given ID exists.
    """

    def get(self, request: http.HttpRequest, image_id: int) -> http.HttpResponse:
        max_rating = settings_queries.get_image_max_rating()
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
                "is_monochromatic": detail.is_monochromatic,
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
            "is_monochromatic": detail.is_monochromatic,
            "max_rating": max_rating,
            "rating_range": rating_range,
        })


class GalleryResults(generic.View):
    """
    Return a paginated page of gallery images for infinite scroll.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        active_filters = _active_filters_from_request(request)
        rating_first = request.GET.get("rating_first", "1") == "1"
        qs = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
        page_obj = django_paginator.Paginator(qs, settings_queries.get_gallery_page_size()).get_page(request.GET.get("page", 1))
        return shortcuts.render(request, "images/_gallery_htmx_scroll_response.html", {"page_obj": page_obj})


class ImageFile(generic.View):
    """
    Serve the raw image file, optionally resized to a given width.

    :raises Http404: if no image with the given ID exists, the file is missing on disk, or the width parameter is not a valid integer.
    """

    image: models.Image

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.image = shortcuts.get_object_or_404(models.Image, pk=kwargs["image_id"])

    def get(self, request: http.HttpRequest, image_id: int) -> http.HttpResponseBase:
        path = Path(self.image.filepath)
        if not path.is_file():
            raise http.Http404
        width_param = request.GET.get("width")
        if width_param:
            try:
                width = int(width_param)
            except ValueError:
                raise http.Http404
            return _resized_image_response(path, width)
        content_type, _ = mimetypes.guess_type(self.image.filepath)
        return http.FileResponse(path.open("rb"), content_type=content_type or "image/jpeg")


class SetImageRating(generic.View):
    """
    Set the star rating for an image and return the updated rating widget.

    :raises Http404: if no image with the given ID exists, or if the rating value is missing or invalid.
    """

    image: models.Image

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.image = shortcuts.get_object_or_404(models.Image, pk=kwargs["image_id"])

    def post(self, request: http.HttpRequest, image_id: int) -> http.HttpResponse:
        try:
            rating = int(request.POST.get("rating", 0))
        except (ValueError, TypeError):
            raise http.Http404
        try:
            image_operations.set_image_rating(image=self.image, rating=rating)
        except image_operations.InvalidImageRatingError:
            raise http.Http404
        max_rating = settings_queries.get_image_max_rating()
        return shortcuts.render(
            request,
            "images/_rating_widget.html",
            {
                "image_id": image_id,
                "rating": self.image.rating,
                "max_rating": max_rating,
                "rating_range": range(1, max_rating + 1),
            },
        )


class SetImagesRating(generic.View):
    """
    Set the same star rating on a batch of selected images.

    Returns an HTML result fragment for the multi-select modal.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        image_ids_raw = request.POST.getlist("image_ids")
        try:
            image_ids = [int(pk) for pk in image_ids_raw]
        except (ValueError, TypeError):
            return http.HttpResponseBadRequest("image_ids must be integers")
        try:
            rating = int(request.POST["rating"])
        except (KeyError, ValueError, TypeError):
            return http.HttpResponseBadRequest("rating must be an integer")

        try:
            result = set_images_rating_uc.set_images_rating(image_ids=image_ids, rating=rating)
        except set_images_rating_uc.InvalidRatingError:
            return shortcuts.render(
                request,
                "images/partials/set_images_rating_result.html",
                {"error": "That rating is not allowed. Please try again."},
            )
        except Exception:
            structlog.get_logger().exception("Unexpected error in SetImagesRating.post")
            return shortcuts.render(
                request,
                "images/partials/set_images_rating_result.html",
                {"error": "An unexpected error occurred. Please try again."},
            )
        return shortcuts.render(
            request,
            "images/partials/set_images_rating_result.html",
            {
                "rated_count": result.rated_count,
                "not_found_count": result.not_found_count,
                "rating": rating,
                "all_succeeded": result.not_found_count == 0,
            },
        )


class RemoveImages(generic.View):
    """
    Remove a batch of selected images from the gallery.

    Images under a registered library folder are also added to that folder's
    ignore list so a later sync does not re-import them; no file is deleted from
    disk. Returns an HTML result fragment for the multi-select modal.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        image_ids_raw = request.POST.getlist("image_ids")
        try:
            image_ids = [int(pk) for pk in image_ids_raw]
        except (ValueError, TypeError):
            return http.HttpResponseBadRequest("image_ids must be integers")

        try:
            result = remove_images_uc.remove_images_from_gallery(image_ids=image_ids)
        except Exception:
            structlog.get_logger().exception("Unexpected error in RemoveImages.post")
            return shortcuts.render(
                request,
                "images/partials/remove_images_result.html",
                {"error": "An unexpected error occurred. Please try again."},
            )
        return shortcuts.render(
            request,
            "images/partials/remove_images_result.html",
            {
                "removed_count": result.removed_count,
                "ignored_count": result.ignored_count,
                "not_found_count": result.not_found_count,
                "all_succeeded": result.all_succeeded,
            },
        )


def _resized_image_response(path: Path, width: int) -> http.FileResponse:
    cache_path, content_type = thumbnail_operations.generate_thumbnail_with_content_type(original_path=path, width=width)
    response = http.FileResponse(cache_path.open("rb"), content_type=content_type)
    response["Cache-Control"] = "max-age=86400"
    return response
