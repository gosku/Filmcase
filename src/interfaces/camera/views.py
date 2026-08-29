import attrs
import structlog

from django import http
from django import shortcuts
from django.views import generic

from src.application.usecases.camera import get_camera_slots as get_camera_slots_uc
from src.application.usecases.camera import push_recipe as push_recipe_uc
from src.data import models
from src.domain.camera import device_config
from src.domain.camera import ptp_device
from src.domain.camera import queries as camera_queries
from src.domain.recipes import queries as recipe_queries

_SLOT_TO_INDEX = {"C1": 1, "C2": 2, "C3": 3, "C4": 4, "C5": 5, "C6": 6, "C7": 7}

# Shown when a request reaches a server-side camera view while the browser owns
# the transport.  400 rather than 503: the server is healthy and behaving as
# configured, and repeating the request unchanged will never succeed, which is
# what 503 would wrongly promise.
_WRONG_TRANSPORT_ERROR = "Filmcase is configured to talk to the camera from your browser."


class SelectSlot(generic.View):
    """
    Display the available camera custom slots for pushing a recipe.

    :raises Http404: if no recipe with the given ID exists, or the recipe has no name.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def dispatch(self, request: http.HttpRequest, *args: object, **kwargs: object) -> http.HttpResponseBase:
        if device_config.is_browser_transport():
            # A stale page or a bookmarked URL should not make a headless server
            # reach for a camera that is plugged into someone else's desk.
            if request.headers.get("HX-Request"):
                return shortcuts.render(
                    request,
                    "recipes/_select_slot_partial.html",
                    {"recipe": self.recipe, "slots": [], "error": _WRONG_TRANSPORT_ERROR},
                )
            return http.JsonResponse({"error": _WRONG_TRANSPORT_ERROR}, status=400)
        if not self.recipe.name:
            raise http.Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
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
    """
    Push a recipe's settings into a selected camera custom slot.

    :raises Http404: if no recipe with the given ID exists, or the slot identifier is not valid.
    """

    recipe: models.FujifilmRecipe
    slot_index: int | None

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])
        self.slot_index = _SLOT_TO_INDEX.get(str(kwargs["slot"]))

    def dispatch(self, request: http.HttpRequest, *args: object, **kwargs: object) -> http.HttpResponseBase:
        if device_config.is_browser_transport():
            if request.headers.get("HX-Request"):
                return shortcuts.render(
                    request,
                    "recipes/_push_result_partial.html",
                    {
                        "error": _WRONG_TRANSPORT_ERROR,
                        "recipe_id": kwargs["recipe_id"],
                        "slot": kwargs["slot"],
                    },
                )
            return http.JsonResponse({"error": _WRONG_TRANSPORT_ERROR}, status=400)
        if self.slot_index is None:
            raise http.Http404
        return super().dispatch(request, *args, **kwargs)

    def post(self, request: http.HttpRequest, recipe_id: int, slot: str) -> http.HttpResponse:
        assert self.slot_index is not None
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


class CameraClientConfig(generic.View):
    """
    Serve the camera configuration a browser needs to drive the camera itself.

    Both halves come from the domain layer so that the two transports run on one
    configuration: the settings decide timing and retry behaviour, and the
    encodings decide what gets written. Neither is duplicated in the JavaScript,
    which is what keeps a table added on the server from needing a second edit
    on the client.

    Served rather than embedded in the page because it is recipe-independent and
    wanted by more than one page, and read once at page load.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        payload = {
            "settings": attrs.asdict(camera_queries.client_camera_settings()),
            "encodings": attrs.asdict(camera_queries.client_camera_encodings()),
        }
        response = http.JsonResponse(payload)
        # The timing settings are tuning values an operator may change between
        # requests, and a stale copy would have the browser writing on delays the
        # server no longer uses.
        response["Cache-Control"] = "no-store"
        return response


class RecipeCameraPayload(generic.View):
    """
    Serve a recipe in the shape the camera write path expects.

    The body is FujifilmRecipeData one field for one key, built by the same
    recipe_from_db() the server-side push calls. That shared call is the point:
    it applies normalization once, so a recipe that reaches the camera through
    the browser has passed through exactly the same domain code as one that
    reaches it through the server.

    :raises Http404: if no recipe with the given ID exists, or the recipe has no name.
    """

    recipe: models.FujifilmRecipe

    def setup(self, request: http.HttpRequest, *args: object, **kwargs: object) -> None:
        super().setup(request, *args, **kwargs)
        self.recipe = shortcuts.get_object_or_404(models.FujifilmRecipe, pk=kwargs["recipe_id"])

    def dispatch(self, request: http.HttpRequest, *args: object, **kwargs: object) -> http.HttpResponseBase:
        # Mirrors SelectSlot: an unnamed recipe cannot be written to a slot, so
        # there is nothing useful to hand the client.
        if not self.recipe.name:
            raise http.Http404
        return super().dispatch(request, *args, **kwargs)

    def get(self, request: http.HttpRequest, recipe_id: int) -> http.HttpResponse:
        recipe_data = recipe_queries.recipe_from_db(recipe=self.recipe)
        response = http.JsonResponse(attrs.asdict(recipe_data))
        # A recipe edited in another tab should not be pushed from a stale copy.
        response["Cache-Control"] = "no-store"
        return response


@attrs.frozen
class _DiagnosticsContext:
    vendor_id: int
    vendor_id_label: str

    @classmethod
    def build(cls) -> "_DiagnosticsContext":
        return cls(
            vendor_id=ptp_device.FUJIFILM_VENDOR_ID,
            vendor_id_label=f"0x{ptp_device.FUJIFILM_VENDOR_ID:04X}",
        )


class CameraDiagnostics(generic.View):
    """
    Report whether this browser can reach a camera over WebUSB from this origin.

    Every check runs in the browser, because the answer depends on where the page was
    loaded from rather than on anything the server can determine: WebUSB is gated on a
    secure context, so it is available over HTTPS and on localhost, and absent over plain
    HTTP to a LAN address no matter which machine the camera is plugged into.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        return shortcuts.render(
            request,
            "camera/diagnostics.html",
            {"diagnostics": _DiagnosticsContext.build(), "active_tab": "camera-diagnostics"},
        )
