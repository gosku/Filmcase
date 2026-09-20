import mimetypes
from datetime import datetime, tzinfo
from pathlib import Path

import structlog
from django import http
from django import shortcuts
from django.utils import timezone as dj_tz
from django.views import generic

from src.application.usecases.images import remove_images as remove_images_uc
from src.application.usecases.images import set_images_rating as set_images_rating_uc
from src.data import models
from src.domain.images import filter_queries
from src.domain.images import operations as image_operations
from src.domain.images import queries as image_queries
from src.domain.images import timeline_queries
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


def _rating_first_from_request(request: http.HttpRequest) -> bool:
    return request.GET.get("rating_first", "1") == "1"


def _timeline_data(
    distribution: timeline_queries.TimelineDistribution,
    today: datetime,
    focus: str | None,
) -> dict[str, object]:
    """Serialize the distribution for the rail's client-side layout."""
    return {
        "today": {"year": today.year, "month": today.month},
        "months": [{"year": m.year, "month": m.month, "count": m.count} for m in distribution.months],
        "undatedCount": distribution.undated_count,
        "total": distribution.total,
        "focus": focus,
    }


def _exclusive_month_end(*, year_month: str, tz: tzinfo) -> datetime:
    """
    Turn a ``YYYY-MM`` jump target into the exclusive upper bound for the seek:
    the first moment of the month *after* the one requested, in *tz*.

    :raises ValueError: if *year_month* is not ``YYYY-MM``.
    """
    year_str, month_str = year_month.split("-")
    year, month = int(year_str), int(month_str)
    if not 1 <= month <= 12:
        raise ValueError(year_month)
    return datetime(year + 1, 1, 1, tzinfo=tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=tz)


def _page_context(page: timeline_queries.ImagePage) -> dict[str, object]:
    return {
        "images": page.images,
        "older_cursor": page.older_cursor,
        "newer_cursor": page.newer_cursor,
        "has_older": page.has_older,
        "has_newer": page.has_newer,
    }


def _focused_page(
    *,
    active_filters: dict[str, list[str]],
    rating_first: bool,
    to_date: str,
    tz: tzinfo,
    limit: int,
) -> tuple[timeline_queries.ImagePage, str | None]:
    """
    Return the page to render and the resolved focus month.

    With a valid ``to_date`` (``YYYY-MM``) it lands on that date; otherwise, and
    for an unparseable value (a page URL should not 500 on a bad param), it
    returns the newest page and no focus.
    """
    if to_date:
        try:
            target = _exclusive_month_end(year_month=to_date, tz=tz)
        except (ValueError, TypeError):
            pass
        else:
            page = timeline_queries.get_images_from_date(
                active_filters=active_filters, rating_first=rating_first, target=target, limit=limit
            )
            return page, to_date
    newest = timeline_queries.get_images_page(
        active_filters=active_filters,
        rating_first=rating_first,
        cursor=None,
        direction=timeline_queries.Direction.OLDER,
        limit=limit,
    )
    return newest, None


def _gallery_context(request: http.HttpRequest) -> dict[str, object]:
    """
    Build the context the gallery page renders with: the current page of images,
    the timeline rail, the filter options and the rating scale.

    Shared by the gallery itself and by a direct image-detail load, which renders
    the same gallery underneath its pre-opened overlay.
    """
    active_filters = _active_filters_from_request(request)
    rating_first = _rating_first_from_request(request)
    tz = dj_tz.get_current_timezone()
    today = dj_tz.localtime()
    # A ``to_date`` in the URL lands on that month (deep-linkable, survives a
    # refresh); otherwise the freshly-loaded gallery is the newest page.
    page, focus = _focused_page(
        active_filters=active_filters,
        rating_first=rating_first,
        to_date=request.GET.get("to_date") or "",
        tz=tz,
        limit=settings_queries.get_gallery_page_size(),
    )
    distribution = timeline_queries.get_timeline_distribution(
        active_filters=active_filters, rating_first=rating_first, tz=tz
    )
    options = filter_queries.get_filter_options(active_filters=active_filters)
    max_rating = settings_queries.get_image_max_rating()
    return {
        **_page_context(page),
        "timeline_data": _timeline_data(distribution, today, focus),
        "to_date": focus or "",
        "sidebar_options": options.sidebar_options,
        "recipe_options": options.recipe_options,
        "rating_first": "1" if rating_first else "0",
        "max_rating": max_rating,
        "rating_range": range(1, max_rating + 1),
    }


class Gallery(generic.View):
    """
    Display the image gallery with filtering and pagination.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        context = _gallery_context(request)
        if request.headers.get("HX-Request"):
            return shortcuts.render(request, "images/_gallery_htmx_filter_response.html", context)
        return shortcuts.render(request, "images/gallery.html", context)


class ImageDetail(generic.View):
    """
    Display the detail view of a single image.

    :raises Http404: if no image with the given ID exists.
    """

    def get(self, request: http.HttpRequest, image_id: int) -> http.HttpResponse:
        active_filters = _active_filters_from_request(request)
        rating_first = _rating_first_from_request(request)
        try:
            detail = image_queries.get_image_detail(
                image_id=image_id,
                active_filters=active_filters,
                rating_first=rating_first,
            )
        except models.Image.DoesNotExist:
            raise http.Http404
        max_rating = settings_queries.get_image_max_rating()
        detail_context: dict[str, object] = {
            "image": detail.image,
            "prev_id": detail.prev_id,
            "next_id": detail.next_id,
            "is_monochromatic": detail.is_monochromatic,
            "max_rating": max_rating,
            "rating_range": range(1, max_rating + 1),
        }
        if request.headers.get("HX-Request"):
            return shortcuts.render(request, "images/_image_detail_partial.html", detail_context)
        # A direct load renders the full gallery with the overlay pre-opened on
        # this image, so closing it reveals the same gallery (and remembered
        # view mode) as ``/images/``.
        return shortcuts.render(
            request,
            "images/gallery.html",
            {**_gallery_context(request), **detail_context, "detail_open": True},
        )


class GalleryResults(generic.View):
    """
    Return one keyset page of gallery images for two-way infinite scroll, or the
    landing page for a date jump.

    Query params:
    - ``direction`` (``older``/``newer``) + ``cursor``: the next scroll page.
    - ``to_date`` (``YYYY-MM``): jump — the landing page around that month.

    ``direction`` is checked first: the scroll sentinels include the whole
    filter-form (which carries ``to_date`` so it survives filter changes), so a
    scroll request also sends ``to_date`` — but it must page from its cursor, not
    re-land at the date. The date is a "go to", not a filter.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        active_filters = _active_filters_from_request(request)
        rating_first = _rating_first_from_request(request)
        limit = settings_queries.get_gallery_page_size()

        direction_param = request.GET.get("direction")
        if direction_param in ("older", "newer"):
            newer = direction_param == "newer"
            try:
                page = timeline_queries.get_images_page(
                    active_filters=active_filters,
                    rating_first=rating_first,
                    cursor=request.GET.get("cursor") or None,
                    direction=timeline_queries.Direction.NEWER if newer else timeline_queries.Direction.OLDER,
                    limit=limit,
                )
            except timeline_queries.InvalidCursor:
                return http.HttpResponseBadRequest("invalid cursor")
            template = "images/_gallery_scroll_newer.html" if newer else "images/_gallery_scroll_older.html"
            return shortcuts.render(request, template, _page_context(page))

        to_date = request.GET.get("to_date")
        if to_date:
            try:
                target = _exclusive_month_end(year_month=to_date, tz=dj_tz.get_current_timezone())
            except (ValueError, TypeError):
                return http.HttpResponseBadRequest("to_date must be YYYY-MM")
            page = timeline_queries.get_images_from_date(
                active_filters=active_filters, rating_first=rating_first, target=target, limit=limit
            )
            return shortcuts.render(request, "images/_gallery_jump_response.html", _page_context(page))

        page = timeline_queries.get_images_page(
            active_filters=active_filters,
            rating_first=rating_first,
            cursor=None,
            direction=timeline_queries.Direction.OLDER,
            limit=limit,
        )
        return shortcuts.render(request, "images/_gallery_scroll_older.html", _page_context(page))


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
