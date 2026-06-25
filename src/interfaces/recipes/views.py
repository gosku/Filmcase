import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urlencode
import attrs as _attrs
import structlog

from django.conf import settings
from django import http
from django import shortcuts
from django import urls
from django.views import generic

from src.interfaces import forms as interface_forms
from src.application.usecases.recipes import build_graph as build_graph_uc
from src.application.usecases.recipes import get_move_preview_distribution as get_move_preview_distribution_uc
from src.application.usecases.recipes import get_recipe_distribution as get_recipe_distribution_uc
from src.application.usecases.recipes import move_recipe_to_version_line as move_recipe_to_version_line_uc
from src.application.usecases.recipes import create_recipe_card as create_recipe_card_uc
from src.application.usecases.recipes import create_recipe_cards_batch as create_recipe_cards_batch_uc
from src.application.usecases.recipes import create_recipe_manually as create_recipe_manually_uc
from src.application.usecases.recipes import create_recipe_version as create_recipe_version_uc
from src.application.usecases.recipes import import_recipes_from_uploaded_files as import_recipes_uc
from src.application.usecases.recipes import import_recipes_from_uploaded_qr_cards as import_qr_cards_uc
from src.application.usecases.recipes import preview_recipe_card as preview_recipe_card_uc
from src.application.usecases.recipes import remove_recipes as remove_recipes_uc
from src.application.usecases.recipes import update_recipe_manually as update_recipe_manually_uc
from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import filter_queries
from src.domain.images import queries as image_queries
from src.domain.recipes import constants as recipe_constants
from src.domain.recipes import dataclasses as recipe_dataclasses
from src.domain.recipes import graph as recipe_graph
from src.domain.recipes import operations as recipe_operations
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes.cards import templates as card_templates


def _recipe_explorer_filters_from_request(request: http.HttpRequest) -> dict[str, list[str]]:
    filters = {
        field: request.GET.getlist(field)
        for field, _ in filter_queries.RECIPE_FILTER_FIELDS
        if request.GET.getlist(field)
    }
    sensor_values = request.GET.getlist("sensors")
    if sensor_values:
        filters["sensors"] = sensor_values
    return filters


class RecipesExplorer(generic.View):
    """
    Display the recipe explorer with filtering and search.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
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


class RecipesExplorerResults(generic.View):
    """
    Return a paginated page of recipes for infinite scroll.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        active_filters = _recipe_explorer_filters_from_request(request)
        name_search = request.GET.get("name_search", "").strip()
        gallery = recipe_queries.get_recipe_gallery_data(
            active_filters=active_filters,
            name_search=name_search,
            page_number=request.GET.get("page", 1),
            page_size=settings.RECIPE_EXPLORER_PAGE_SIZE,
        )
        return shortcuts.render(request, "recipes/partials/htmx_scroll_response.html", {"page_obj": gallery.page_obj})


class RecipeDetail(generic.View):
    """
    Display the detail page for a single recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        try:
            detail = recipe_queries.get_recipe_detail(recipe_id=recipe_id)
        except models.FujifilmRecipe.DoesNotExist:
            raise http.Http404
        ctx = {"recipe": detail.recipe, "is_monochromatic": detail.is_monochromatic, "settings_editable": detail.settings_editable}
        if request.headers.get("HX-Request"):
            return shortcuts.render(request, "recipes/partials/recipe_detail.html", ctx)
        return shortcuts.render(request, "recipes/recipe_detail.html", ctx)


class RecipeDistribution(generic.View):
    """
    Return the usage distribution chart for a recipe across its version line.

    :raises Http404: if no recipe with the given ID exists.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        try:
            ctx = get_recipe_distribution_uc.get_recipe_distribution(
                recipe_id=recipe_id,
                duration=request.GET.get("scale"),
            )
        except get_recipe_distribution_uc.RecipeNotFoundError:
            raise http.Http404
        except (
            get_recipe_distribution_uc.InvalidDurationError,
            get_recipe_distribution_uc.RecipeNotInVersionLineError,
        ):
            return http.HttpResponseBadRequest()
        distribution_data = {
            "versions": [
                {
                    "recipe_id": v.recipe_id,
                    "label": v.label,
                    "color": v.color,
                    "is_current": v.is_current,
                    "image_count": v.image_count,
                }
                for v in ctx.versions
            ],
            "buckets": [
                {
                    "label": b.label,
                    "counts": {str(rid): count for rid, count in b.counts.items()},
                }
                for b in ctx.buckets
            ],
        }
        return shortcuts.render(request, "recipes/partials/recipe_distribution.html", {
            "ctx": ctx,
            "distribution_json": json.dumps(distribution_data),
        })


class MoveRecipeToVersionLine(generic.View):
    """
    Display and handle the form for moving a recipe to a different version line group.

    :raises Http404: if no recipe with the given ID exists.
    """

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(
            models.FujifilmRecipe, pk=kwargs["recipe_id"]
        )

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        return shortcuts.render(request, "recipes/partials/move_version_line_modal.html", {
            "recipe": self.recipe,
        })

    def post(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        try:
            destination_group_id = int(request.POST["destination_group_id"])
            position_raw = request.POST.get("position")
            position = int(position_raw) if position_raw else None
        except (KeyError, ValueError):
            return http.HttpResponseBadRequest()

        try:
            move_recipe_to_version_line_uc.move_recipe_to_version_line(
                recipe_id=recipe_id,
                destination_group_id=destination_group_id,
                position=position,
            )
        except (
            move_recipe_to_version_line_uc.RecipeNotInVersionLineError,
            move_recipe_to_version_line_uc.VersionLineGroupNotFoundError,
            move_recipe_to_version_line_uc.CannotMoveToSameGroupError,
            move_recipe_to_version_line_uc.InvalidVersionLinePositionError,
        ):
            return http.HttpResponseBadRequest()

        response = http.HttpResponse()
        response["HX-Redirect"] = urls.reverse("recipe-detail", kwargs={"recipe_id": recipe_id})
        return response


class MoveRecipeToVersionLineSearch(generic.View):
    """
    Search for candidate version line groups to move a recipe into.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        name_search = request.GET.get("name_search", "")
        try:
            candidates = recipe_queries.search_recipes_for_version_line_move(
                source_recipe_id=recipe_id,
                name_search=name_search,
            )
        except recipe_queries.RecipeNotInVersionLineError:
            return http.HttpResponseBadRequest()
        return shortcuts.render(
            request,
            "recipes/partials/move_version_line_search_results.html",
            {"candidates": candidates, "recipe_id": recipe_id},
        )


class MoveRecipeToVersionLinePreview(generic.View):
    """
    Preview the distribution impact of moving a recipe to a different version line position.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        try:
            destination_group_id = int(request.GET["destination_group_id"])
        except (KeyError, ValueError):
            return http.HttpResponseBadRequest()

        position_raw = request.GET.get("position")
        position = int(position_raw) if position_raw else None

        try:
            ctx = get_move_preview_distribution_uc.get_move_preview_distribution(
                source_recipe_id=recipe_id,
                destination_group_id=destination_group_id,
                position=position,
                duration=request.GET.get("scale"),
            )
        except (
            get_move_preview_distribution_uc.VersionLineGroupNotFoundError,
            get_move_preview_distribution_uc.InvalidDurationError,
        ):
            return http.HttpResponseBadRequest()

        distribution_data = {
            "versions": [
                {
                    "recipe_id": v.recipe_id,
                    "label": v.label,
                    "color": v.color,
                    "is_current": v.is_current,
                    "image_count": v.image_count,
                }
                for v in ctx.versions
            ],
            "buckets": [
                {
                    "label": b.label,
                    "counts": {str(rid): count for rid, count in b.counts.items()},
                }
                for b in ctx.buckets
            ],
        }
        group_member_count = len(ctx.versions)
        resolved_position = position if position is not None else group_member_count
        return shortcuts.render(
            request,
            "recipes/partials/move_version_line_preview.html",
            {
                "ctx": ctx,
                "distribution_json": json.dumps(distribution_data),
                "destination_group_id": destination_group_id,
                "group_member_count": group_member_count,
                "position": resolved_position,
                "position_range": range(1, group_member_count + 1),
                "recipe_id": recipe_id,
            },
        )


_RECIPES_GRAPH_DEFAULT_FILM_SIM = "Provia"


def _root_fields_json(root_id: int | None) -> list[dict[str, str]]:
    if root_id is None:
        return []
    try:
        root = models.FujifilmRecipe.objects.get(pk=root_id)
    except models.FujifilmRecipe.DoesNotExist:
        return []
    return [{"field": f.field, "value": f.value} for f in recipe_queries.get_recipe_all_fields(recipe=root)]


class RecipesGraph(generic.View):
    """
    Display the network graph of all recipes for a given film simulation.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
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


class RecipeGraph(generic.View):
    """
    Display the network graph centered on a specific recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        all_recipes = list(models.FujifilmRecipe.objects.all())
        max_distance: int = settings.RECIPE_GRAPH_MAX_DISTANCE
        image_counts = recipe_queries.get_image_counts(recipe_pks=[r.pk for r in all_recipes])
        graph_data = recipe_graph.build_recipe_graph(
            root=self.recipe,
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
        root_fields = [{"field": f.field, "value": f.value} for f in recipe_queries.get_recipe_all_fields(recipe=self.recipe)]
        root_label = self.recipe.name or f"#{self.recipe.pk}"
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


class RecipeImages(generic.View):
    """
    Return the list of images associated with a recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
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


class RecipeCompareImage(generic.View):
    """
    Return image data for side-by-side recipe comparison.

    :raises Http404: if no recipe or image with the given IDs exists.
    """

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def get(self, request: http.HttpRequest, recipe_id: int, image_id: int) -> http.HttpResponse:
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


class SetRecipeName(generic.View):
    """
    Set the display name of a recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def post(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
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


class SetRecipeCoverImage(generic.View):
    """
    Set the cover image for a recipe.

    :raises Http404: if the recipe or image does not exist, or the image is not associated with the recipe.
    """

    def post(self, request: http.HttpRequest, recipe_id: int, image_id: int) -> http.HttpResponse:
        try:
            recipe_operations.set_cover_image_for_recipe(recipe_id=recipe_id, image_id=image_id)
        except (
            recipe_operations.RecipeNotFoundError,
            recipe_operations.ImageNotFoundError,
            recipe_operations.ImageNotAssociatedToRecipeError,
        ):
            raise http.Http404
        return shortcuts.render(
            request,
            "images/_set_cover_image_btn.html",
            {"recipe_id": recipe_id, "image_id": image_id, "is_cover": True},
        )


class RemoveRecipes(generic.View):
    """
    Remove one or more recipes from the library.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        recipe_ids_raw = request.POST.getlist("recipe_ids")
        try:
            recipe_ids = [int(pk) for pk in recipe_ids_raw]
        except (ValueError, TypeError):
            return http.HttpResponseBadRequest("recipe_ids must be integers")
        remove_recipe_card_file = request.POST.get("remove_recipe_card_file") == "on"
        try:
            result = remove_recipes_uc.remove_recipes(
                recipe_ids=recipe_ids,
                remove_recipe_card_file=remove_recipe_card_file,
            )
        except Exception:
            structlog.get_logger().exception("Unexpected error in RemoveRecipes.post")
            return shortcuts.render(
                request,
                "recipes/partials/remove_recipes_result.html",
                {"error": "An unexpected error occurred. Please try again."},
            )
        return shortcuts.render(
            request,
            "recipes/partials/remove_recipes_result.html",
            {
                "removed_count": result.removed_count,
                "failures": result.failures,
                "all_succeeded": not result.failures,
            },
        )


_BATCH_ZIP_NAME_RE = re.compile(r"^recipe_cards_[0-9a-f]{8}\.zip$")
_BATCH_RESULT_TEMPLATE = "recipes/partials/create_recipe_cards_batch_result.html"


class CreateRecipeCardsBatch(generic.View):
    """
    Generate recipe cards for a batch of recipes.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        recipe_ids_raw = request.POST.getlist("recipe_ids")
        try:
            recipe_ids = [int(pk) for pk in recipe_ids_raw]
        except (ValueError, TypeError):
            return http.HttpResponseBadRequest("recipe_ids must be integers")
        try:
            result = create_recipe_cards_batch_uc.create_recipe_cards_batch(
                recipe_ids=recipe_ids,
            )
        except Exception:
            structlog.get_logger().exception(
                "Unexpected error in CreateRecipeCardsBatch.post"
            )
            return shortcuts.render(
                request,
                _BATCH_RESULT_TEMPLATE,
                {"error": "An unexpected error occurred. Please try again."},
            )
        zip_download_url = None
        if result.zip_path is not None:
            zip_download_url = urls.reverse(
                "recipes-card-zip-download", args=[result.zip_path.name]
            )
        return shortcuts.render(
            request,
            _BATCH_RESULT_TEMPLATE,
            {
                "created_count": result.created_count,
                "failures": result.failures,
                "all_succeeded": result.created_count > 0 and not result.failures,
                "zip_download_url": zip_download_url,
            },
        )


class RecipeCardZipDownload(generic.View):
    """
    Download a zip archive of generated recipe cards.

    :raises Http404: if the filename does not match the expected pattern or the file no longer exists.
    """

    def get(self, request: http.HttpRequest, filename: str) -> http.FileResponse:
        # The filename pattern is strict (no path separators) so it cannot be used
        # to escape the temp directory.
        if not _BATCH_ZIP_NAME_RE.fullmatch(filename):
            raise http.Http404
        zip_path = Path(tempfile.gettempdir()) / filename
        if not zip_path.is_file():
            raise http.Http404
        return http.FileResponse(
            zip_path.open("rb"),
            as_attachment=True,
            filename=filename,
            content_type="application/zip",
        )


class ImportRecipesFromUploadedFiles(generic.View):
    """
    Import recipes from uploaded image files.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        uploaded = request.FILES.getlist("images")
        if not uploaded:
            return shortcuts.render(
                request,
                "recipes/partials/_import_result.html",
                {"error": "No files were uploaded."},
            )

        files = [
            recipe_dataclasses.UploadedFile(name=f.name or "", content=f.read())
            for f in uploaded
        ]

        try:
            result = import_recipes_uc.import_recipes_from_uploaded_files(files=files)
        except Exception:
            structlog.get_logger().exception("Unexpected error in ImportRecipesFromUploadedFiles.post")
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


class ImportRecipesFromUploadedQrCards(generic.View):
    """
    Import recipes from uploaded QR card images.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        uploaded = request.FILES.getlist("images")
        if not uploaded:
            return shortcuts.render(
                request,
                "recipes/partials/_import_result.html",
                {"error": "No files were uploaded."},
            )

        files = [
            recipe_dataclasses.UploadedFile(name=f.name or "", content=f.read())
            for f in uploaded
        ]

        try:
            result = import_qr_cards_uc.import_recipes_from_uploaded_qr_cards(files=files)
        except Exception:
            structlog.get_logger().exception("Unexpected error in ImportRecipesFromUploadedQrCards.post")
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


class RecipePathDeltas(generic.View):
    """
    Return the field differences along a recipe path in the network graph.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
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


def _resolve_card_template(
    label_style: str,
    bg_effect: str,
) -> card_templates.CardTemplate:
    key = ("long" if label_style == "long" else "short") + "_label" + ("_sharp" if bg_effect == "sharp" else "")
    return card_templates.TEMPLATES.get(key, card_templates.LONG_LABEL)


def _resolve_info_side(value: str) -> card_templates.InfoSide:
    return "right" if value == "right" else "left"


@_attrs.frozen
class _RecipeCardModalContext:
    pk: int
    display_name: str

    @classmethod
    def from_model(cls, recipe: models.FujifilmRecipe) -> "_RecipeCardModalContext":
        name = recipe.name or f"{recipe.film_simulation} #{recipe.pk}"
        return cls(pk=recipe.pk, display_name=name)


@_attrs.frozen
class _ImageThumbnailContext:
    pk: int

    @classmethod
    def from_model(cls, image: models.Image) -> "_ImageThumbnailContext":
        return cls(pk=image.pk)


@_attrs.frozen
class _RecipeCardResultContext:
    pk: int
    recipe_id: int

    @classmethod
    def from_model(cls, card: models.RecipeCard) -> "_RecipeCardResultContext":
        return cls(pk=card.pk, recipe_id=card.recipe_id)


class RecipeCardModal(generic.View):
    """
    Display the recipe card creation modal for a recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        images = models.Image.objects.filter(
            fujifilm_recipe=self.recipe,
        ).order_by("-rating", "-taken_at")[:12]
        return shortcuts.render(
            request,
            "recipes/partials/recipe_card_modal.html",
            {
                "recipe": _RecipeCardModalContext.from_model(self.recipe),
                "images": [_ImageThumbnailContext.from_model(img) for img in images],
            },
        )


class RecipeCardPreview(generic.View):
    """
    Generate and display a preview of a recipe card.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        image_id_raw = request.GET.get("image_id")
        image_id = int(image_id_raw) if image_id_raw else None
        template = _resolve_card_template(
            label_style=request.GET.get("label_style", "long"),
            bg_effect=request.GET.get("bg_effect", "blur"),
        )
        info_side = _resolve_info_side(request.GET.get("info_side", "left"))
        try:
            preview_path = preview_recipe_card_uc.preview_recipe_card(
                recipe_id=recipe_id,
                image_id=image_id,
                template=template,
                info_side=info_side,
            )
        except Exception:
            structlog.get_logger().exception("Unexpected error generating recipe card preview")
            return shortcuts.render(
                request,
                "recipes/partials/recipe_card_result.html",
                {"error": "Could not generate preview."},
            )
        return shortcuts.render(
            request,
            "recipes/partials/recipe_card_result.html",
            {
                "preview_path": str(preview_path),
                "recipe_id": recipe_id,
                "image_id": image_id,
                "label_style": request.GET.get("label_style", "long"),
                "bg_effect": request.GET.get("bg_effect", "blur"),
                "info_side": info_side,
            },
        )


class RecipeCardPreviewFile(generic.View):
    """
    Serve the raw preview image file for a recipe card.

    :raises Http404: if the preview image cannot be generated.
    """

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.FileResponse:
        image_id_raw = request.GET.get("image_id")
        image_id = int(image_id_raw) if image_id_raw else None
        template = _resolve_card_template(
            label_style=request.GET.get("label_style", "long"),
            bg_effect=request.GET.get("bg_effect", "blur"),
        )
        info_side = _resolve_info_side(request.GET.get("info_side", "left"))
        try:
            preview_path = preview_recipe_card_uc.preview_recipe_card(
                recipe_id=recipe_id,
                image_id=image_id,
                template=template,
                info_side=info_side,
            )
        except Exception:
            structlog.get_logger().exception("Unexpected error generating recipe card preview file")
            raise http.Http404
        return http.FileResponse(preview_path.open("rb"), content_type="image/jpeg")


class CreateRecipeCard(generic.View):
    """
    Create and persist a recipe card for a recipe.

    :raises Http404: if no recipe with the given ID exists.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(
            models.FujifilmRecipe, pk=kwargs["recipe_id"]
        )

    def post(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        image_id_raw = request.POST.get("image_id")
        image_id = int(image_id_raw) if image_id_raw else None
        template = _resolve_card_template(
            label_style=request.POST.get("label_style", "long"),
            bg_effect=request.POST.get("bg_effect", "blur"),
        )
        info_side = _resolve_info_side(request.POST.get("info_side", "left"))
        try:
            card = create_recipe_card_uc.create_recipe_card(
                recipe_id=recipe_id,
                image_id=image_id,
                template=template,
                info_side=info_side,
            )
        except Exception:
            structlog.get_logger().exception("Unexpected error creating recipe card")
            return shortcuts.render(
                request,
                "recipes/partials/recipe_card_result.html",
                {"error": "Something unexpected happened."},
            )
        return shortcuts.render(
            request,
            "recipes/partials/recipe_card_result.html",
            {"card": _RecipeCardResultContext.from_model(card), "created": True},
        )


class RecipeCardFile(generic.View):
    """
    Serve the raw image file of a saved recipe card.

    :raises Http404: if no recipe card with the given ID exists.
    """

    card: models.RecipeCard

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.card = shortcuts.get_object_or_404(models.RecipeCard, pk=kwargs["card_id"])

    def get(self, request: http.HttpRequest, card_id: int) -> http.FileResponse:
        return http.FileResponse(Path(self.card.filepath).open("rb"), content_type="image/jpeg")


def _parse_white_balance_for_form(white_balance: str) -> tuple[str, int | None]:
    if white_balance.endswith("K"):
        try:
            return "Kelvin", int(white_balance[:-1])
        except ValueError:
            pass
    return white_balance, None


class EditRecipe(generic.FormView):  # type: ignore[type-arg]
    """
    Display and handle the form for editing a recipe's settings.

    :raises Http404: if no recipe with the given ID exists.
    """

    template_name = "recipes/edit_recipe.html"
    form_class = interface_forms.CreateRecipe
    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def get_initial(self) -> dict[str, object]:
        r = self.recipe
        wb_value, kelvin = _parse_white_balance_for_form(r.white_balance)
        return {
            "name": r.name,
            "film_simulation": r.film_simulation,
            "dynamic_range": r.dynamic_range,
            "d_range_priority": r.d_range_priority,
            "grain_roughness": r.grain_roughness,
            "grain_size": r.grain_size,
            "color_chrome_effect": r.color_chrome_effect,
            "color_chrome_fx_blue": r.color_chrome_fx_blue,
            "white_balance": wb_value,
            "kelvin_temperature": kelvin,
            "white_balance_red": r.white_balance_red,
            "white_balance_blue": r.white_balance_blue,
            "highlight": r.highlight,
            "shadow": r.shadow,
            "color": r.color,
            "sharpness": r.sharpness,
            "high_iso_nr": r.high_iso_nr,
            "clarity": r.clarity,
            "monochromatic_color_warm_cool": r.monochromatic_color_warm_cool,
            "monochromatic_color_magenta_green": r.monochromatic_color_magenta_green,
            "sensors": list(r.sensors.values_list("name", flat=True)),
            "description": r.description,
        }

    def get_form_kwargs(self) -> dict[str, object]:
        kwargs = super().get_form_kwargs()
        if self.request.method == "POST" and not recipe_queries.recipe_is_editable(recipe_id=self.recipe.pk):
            data = kwargs["data"].copy()
            r = self.recipe
            wb_value, kelvin = _parse_white_balance_for_form(r.white_balance)
            settings_defaults: dict[str, str] = {
                "film_simulation": r.film_simulation,
                "dynamic_range": r.dynamic_range or "",
                "d_range_priority": r.d_range_priority,
                "grain_roughness": r.grain_roughness,
                "grain_size": r.grain_size or "",
                "color_chrome_effect": r.color_chrome_effect,
                "color_chrome_fx_blue": r.color_chrome_fx_blue,
                "white_balance": wb_value,
                "white_balance_red": str(r.white_balance_red),
                "white_balance_blue": str(r.white_balance_blue),
                **({"highlight": str(r.highlight)} if r.highlight is not None else {}),
                **({"shadow": str(r.shadow)} if r.shadow is not None else {}),
                **({"color": str(r.color)} if r.color is not None else {}),
                **({"monochromatic_color_warm_cool": str(r.monochromatic_color_warm_cool)} if r.monochromatic_color_warm_cool is not None else {}),
                **({"monochromatic_color_magenta_green": str(r.monochromatic_color_magenta_green)} if r.monochromatic_color_magenta_green is not None else {}),
                "sharpness": str(r.sharpness) if r.sharpness is not None else "0",
                "high_iso_nr": str(r.high_iso_nr) if r.high_iso_nr is not None else "0",
                "clarity": str(r.clarity) if r.clarity is not None else "0",
            }
            if kelvin is not None:
                settings_defaults["kelvin_temperature"] = str(kelvin)
            for key, value in settings_defaults.items():
                if key not in data:
                    data[key] = value
            kwargs["data"] = data
        return kwargs

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context: dict[str, object] = super().get_context_data(**kwargs)
        context["recipe"] = self.recipe
        context["is_settings_editable"] = recipe_queries.recipe_is_editable(recipe_id=self.recipe.pk)
        context["monochromatic_film_sims_json"] = json.dumps(
            sorted(recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS)
        )
        return context

    def form_valid(self, form: interface_forms.CreateRecipe) -> http.HttpResponse:
        cd = form.cleaned_data
        wb = cd["white_balance"]
        kelvin_temp = cd.get("kelvin_temperature")
        white_balance_str = f"{kelvin_temp}K" if wb == "Kelvin" else wb

        def _to_str(value: object) -> str | None:
            return None if value is None else str(value)

        recipe_data = image_dataclasses.FujifilmRecipeData(
            name=cd["name"],
            film_simulation=cd["film_simulation"],
            d_range_priority=cd["d_range_priority"],
            grain_roughness=cd["grain_roughness"],
            color_chrome_effect=cd["color_chrome_effect"],
            color_chrome_fx_blue=cd["color_chrome_fx_blue"],
            white_balance=white_balance_str,
            white_balance_red=cd["white_balance_red"],
            white_balance_blue=cd["white_balance_blue"],
            sharpness=str(cd["sharpness"]),
            high_iso_nr=str(cd["high_iso_nr"]),
            clarity=str(cd["clarity"]),
            dynamic_range=cd.get("dynamic_range"),
            grain_size=cd.get("grain_size"),
            highlight=_to_str(cd.get("highlight")),
            shadow=_to_str(cd.get("shadow")),
            color=_to_str(cd.get("color")),
            monochromatic_color_warm_cool=_to_str(cd.get("monochromatic_color_warm_cool")),
            monochromatic_color_magenta_green=_to_str(cd.get("monochromatic_color_magenta_green")),
            sensors=tuple(cd.get("sensors") or ()),
            description=cd.get("description") or "",
        )

        try:
            update_recipe_manually_uc.update_recipe_manually(recipe=self.recipe, data=recipe_data)
        except update_recipe_manually_uc.RecipeCannotBeEditedError:
            form.add_error(None, "This recipe's settings cannot be changed because it has associated images. You can still edit the name.")
            return self.form_invalid(form)
        except update_recipe_manually_uc.RecipeAlreadyExistsError:
            form.add_error(None, "A recipe with these settings already exists.")
            return self.form_invalid(form)
        except Exception:
            structlog.get_logger().exception("Unexpected error in EditRecipe.form_valid")
            form.add_error(None, "An unexpected error occurred editing the recipe.")
            return self.form_invalid(form)

        redirect_url = shortcuts.resolve_url("recipe-detail", recipe_id=self.recipe.pk)
        if self.recipe.name:
            redirect_url += "?" + urlencode({"name_search": self.recipe.name})
        return shortcuts.redirect(redirect_url)


class CreateRecipeVersion(generic.FormView):  # type: ignore[type-arg]
    """
    Display and handle the form for creating a new version of a recipe in its version line.

    :raises Http404: if no recipe with the given ID exists.
    """

    template_name = "recipes/create_recipe_version.html"
    form_class = interface_forms.CreateRecipe
    recipe: models.FujifilmRecipe
    source_member: models.RecipeGroupMember | None

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        self.source_member = models.RecipeGroupMember.objects.filter(
            recipe=self.recipe,
            group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
        ).first()

    def dispatch(self, request: http.HttpRequest, *args: object, **kwargs: object) -> http.HttpResponseBase:
        if self.source_member is None:
            return http.HttpResponseBadRequest()
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self) -> dict[str, object]:
        r = self.recipe
        wb_value, kelvin = _parse_white_balance_for_form(r.white_balance)
        return {
            "name": r.name,
            "film_simulation": r.film_simulation,
            "dynamic_range": r.dynamic_range,
            "d_range_priority": r.d_range_priority,
            "grain_roughness": r.grain_roughness,
            "grain_size": r.grain_size,
            "color_chrome_effect": r.color_chrome_effect,
            "color_chrome_fx_blue": r.color_chrome_fx_blue,
            "white_balance": wb_value,
            "kelvin_temperature": kelvin,
            "white_balance_red": r.white_balance_red,
            "white_balance_blue": r.white_balance_blue,
            "highlight": r.highlight,
            "shadow": r.shadow,
            "color": r.color,
            "sharpness": r.sharpness,
            "high_iso_nr": r.high_iso_nr,
            "clarity": r.clarity,
            "monochromatic_color_warm_cool": r.monochromatic_color_warm_cool,
            "monochromatic_color_magenta_green": r.monochromatic_color_magenta_green,
            "sensors": list(r.sensors.values_list("name", flat=True)),
            "description": r.description,
        }

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context: dict[str, object] = super().get_context_data(**kwargs)
        context["recipe"] = self.recipe
        context["monochromatic_film_sims_json"] = json.dumps(
            sorted(recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS)
        )
        return context

    def form_valid(self, form: interface_forms.CreateRecipe) -> http.HttpResponse:
        assert self.source_member is not None
        cd = form.cleaned_data
        wb = cd["white_balance"]
        kelvin_temp = cd.get("kelvin_temperature")
        white_balance_str = f"{kelvin_temp}K" if wb == "Kelvin" else wb

        def _to_str(value: object) -> str | None:
            return None if value is None else str(value)

        recipe_data = image_dataclasses.FujifilmRecipeData(
            name=cd["name"],
            film_simulation=cd["film_simulation"],
            d_range_priority=cd["d_range_priority"],
            grain_roughness=cd["grain_roughness"],
            color_chrome_effect=cd["color_chrome_effect"],
            color_chrome_fx_blue=cd["color_chrome_fx_blue"],
            white_balance=white_balance_str,
            white_balance_red=cd["white_balance_red"],
            white_balance_blue=cd["white_balance_blue"],
            sharpness=str(cd["sharpness"]),
            high_iso_nr=str(cd["high_iso_nr"]),
            clarity=str(cd["clarity"]),
            dynamic_range=cd.get("dynamic_range"),
            grain_size=cd.get("grain_size"),
            highlight=_to_str(cd.get("highlight")),
            shadow=_to_str(cd.get("shadow")),
            color=_to_str(cd.get("color")),
            monochromatic_color_warm_cool=_to_str(cd.get("monochromatic_color_warm_cool")),
            monochromatic_color_magenta_green=_to_str(cd.get("monochromatic_color_magenta_green")),
            sensors=tuple(cd.get("sensors") or ()),
            description=cd.get("description") or "",
        )

        try:
            new_recipe = create_recipe_version_uc.create_recipe_version(
                data=recipe_data,
                group_id=self.source_member.group.pk,
            )
        except create_recipe_version_uc.RecipeAlreadyExistsError as exc:
            existing_name = exc.name if exc.name else "(unnamed)"
            form.add_error(None, f'A recipe like this already exists with name "{existing_name}".')
            return self.form_invalid(form)
        except Exception:
            structlog.get_logger().exception("Unexpected error in CreateRecipeVersion.form_valid")
            form.add_error(None, "An unexpected error occurred creating the recipe.")
            return self.form_invalid(form)

        redirect_url = shortcuts.resolve_url("recipe-detail", recipe_id=new_recipe.pk)
        if new_recipe.name:
            redirect_url += "?" + urlencode({"name_search": new_recipe.name})
        return shortcuts.redirect(redirect_url)


class CreateRecipe(generic.FormView):  # type: ignore[type-arg]
    """
    Display and handle the form for creating a new recipe manually.
    """

    template_name = "recipes/create_recipe.html"
    form_class = interface_forms.CreateRecipe

    def get_context_data(self, **kwargs: object) -> dict[str, object]:
        context: dict[str, object] = super().get_context_data(**kwargs)
        context["monochromatic_film_sims_json"] = json.dumps(
            sorted(recipe_constants.MONOCHROMATIC_FILM_SIMULATIONS)
        )
        return context

    def form_valid(self, form: interface_forms.CreateRecipe) -> http.HttpResponse:
        cd = form.cleaned_data
        wb = cd["white_balance"]
        kelvin_temp = cd.get("kelvin_temperature")
        white_balance_str = f"{kelvin_temp}K" if wb == "Kelvin" else wb

        def _to_str(value: object) -> str | None:
            return None if value is None else str(value)

        recipe_data = image_dataclasses.FujifilmRecipeData(
            name=cd["name"],
            film_simulation=cd["film_simulation"],
            d_range_priority=cd["d_range_priority"],
            grain_roughness=cd["grain_roughness"],
            color_chrome_effect=cd["color_chrome_effect"],
            color_chrome_fx_blue=cd["color_chrome_fx_blue"],
            white_balance=white_balance_str,
            white_balance_red=cd["white_balance_red"],
            white_balance_blue=cd["white_balance_blue"],
            sharpness=str(cd["sharpness"]),
            high_iso_nr=str(cd["high_iso_nr"]),
            clarity=str(cd["clarity"]),
            dynamic_range=cd.get("dynamic_range"),
            grain_size=cd.get("grain_size"),
            highlight=_to_str(cd.get("highlight")),
            shadow=_to_str(cd.get("shadow")),
            color=_to_str(cd.get("color")),
            monochromatic_color_warm_cool=_to_str(cd.get("monochromatic_color_warm_cool")),
            monochromatic_color_magenta_green=_to_str(cd.get("monochromatic_color_magenta_green")),
            sensors=tuple(cd.get("sensors") or ()),
            description=cd.get("description") or "",
        )

        try:
            recipe = create_recipe_manually_uc.create_recipe_manually(data=recipe_data)
        except create_recipe_manually_uc.RecipeAlreadyExistsError as exc:
            existing_name = exc.name if exc.name else "(unnamed)"
            form.add_error(None, f'A recipe like this already exists with name "{existing_name}".')
            return self.render_to_response(self.get_context_data(form=form))
        except Exception:
            structlog.get_logger().exception("Unexpected error in CreateRecipe.form_valid")
            form.add_error(None, "An unexpected error occurred creating the recipe.")
            return self.render_to_response(self.get_context_data(form=form))

        redirect_url = shortcuts.resolve_url("recipe-detail", recipe_id=recipe.pk)
        if recipe.name:
            redirect_url += "?" + urlencode({"name_search": recipe.name})
        return shortcuts.redirect(redirect_url)
