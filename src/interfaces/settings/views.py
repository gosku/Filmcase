from collections.abc import Mapping
from urllib.parse import urlencode

import attrs

from django import http, shortcuts, urls
from django.conf import settings as django_settings
from django.forms.boundfield import BoundField
from django.views import generic

from src.application.usecases.images import trigger_thumbnail_generation as trigger_thumbnail_generation_uc
from src.application.usecases.settings import get_app_settings as get_app_settings_uc
from src.application.usecases.settings import update_app_settings as update_app_settings_uc
from src.interfaces import forms

_TEMPLATE = "settings/preferences.html"


class Preferences(generic.View):
    """
    Show and edit the user-adjustable application settings.

    On GET the form is seeded with the current values, which are the env
    defaults until something is saved and the database values thereafter. A
    valid POST saves every value and takes effect immediately, without a restart.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        form = forms.Preferences(initial=self._current_initial())
        return self._render(request, form, thumbnail_banner=_thumbnail_banner(request))

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        form = forms.Preferences(request.POST)
        if not form.is_valid():
            return self._render(request, form)

        update_app_settings_uc.update_app_settings(values=form.to_app_settings())

        # Re-read so the reloaded form reflects exactly what was persisted.
        saved_form = forms.Preferences(initial=self._current_initial())
        return self._render(request, saved_form, saved=True)

    @staticmethod
    def _current_initial() -> dict[str, object]:
        return forms.Preferences.initial_from(get_app_settings_uc.get_app_settings())

    def _render(
        self,
        request: http.HttpRequest,
        form: forms.Preferences,
        *,
        saved: bool = False,
        thumbnail_banner: "_ThumbnailBanner | None" = None,
    ) -> http.HttpResponse:
        return shortcuts.render(
            request,
            _TEMPLATE,
            {
                "form": form,
                "fieldsets": self._fieldsets(form),
                "saved": saved,
                "thumbnail_banner": thumbnail_banner,
                "active_tab": "preferences",
            },
        )

    @staticmethod
    def _fieldsets(form: forms.Preferences) -> "list[_Fieldset]":
        """
        Group the form's bound fields into the app sections declared in
        ``settings.CONSTANCE_CONFIG_FIELDSETS`` so the page mirrors the rest of
        Filmcase.

        The section that holds ``THUMBNAIL_WIDTHS`` also carries the thumbnail
        action, so the "Generate thumbnails" button renders at the end of that
        section rather than the template hard-coding a section name.
        """
        sections: list[_Fieldset] = []
        for title, keys in django_settings.CONSTANCE_CONFIG_FIELDSETS.items():
            sections.append(
                _Fieldset(
                    title=title,
                    fields=[form[key.lower()] for key in keys],
                    show_thumbnail_action="THUMBNAIL_WIDTHS" in keys,
                )
            )
        return sections


class GenerateThumbnails(generic.View):
    """
    Pre-generate cached thumbnails for the whole collection from the web app,
    then redirect back to Preferences with a banner describing the outcome.
    """

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        try:
            summary = trigger_thumbnail_generation_uc.trigger_thumbnail_generation()
        except trigger_thumbnail_generation_uc.CeleryWorkerUnavailable:
            return self._redirect({"thumbnails": "no-worker"})

        if summary.ran_in_background:
            return self._redirect({"thumbnails": "started"})
        return self._redirect(
            {"thumbnails": "queued", "enqueued": summary.enqueued, "cached": summary.already_cached}
        )

    @staticmethod
    def _redirect(params: Mapping[str, object]) -> http.HttpResponse:
        return shortcuts.redirect(f"{urls.reverse('app-settings')}?{urlencode(params)}")


@attrs.frozen
class _Fieldset:
    title: str
    fields: list[BoundField]
    show_thumbnail_action: bool


@attrs.frozen
class _ThumbnailBanner:
    message: str
    is_error: bool


def _int_param(request: http.HttpRequest, name: str) -> int:
    try:
        return max(0, int(request.GET.get(name, "0")))
    except (TypeError, ValueError):
        return 0


def _thumbnail_banner(request: http.HttpRequest) -> "_ThumbnailBanner | None":
    """
    Build the banner for a thumbnail run's outcome from the redirect's query
    flags, or None when there is no thumbnail flag on the request.
    """
    status = request.GET.get("thumbnails")
    if status == "no-worker":
        return _ThumbnailBanner(
            message="No image worker is running to generate thumbnails. Start one with 'make worker'.",
            is_error=True,
        )
    if status == "started":
        return _ThumbnailBanner(message="Generating thumbnails in the background.", is_error=False)
    if status == "queued":
        enqueued = _int_param(request, "enqueued")
        cached = _int_param(request, "cached")
        if enqueued == 0:
            message = "Thumbnails are already up to date."
        elif cached:
            message = f"Queued {enqueued} thumbnails for generation ({cached} already cached)."
        else:
            message = f"Queued {enqueued} thumbnails for generation."
        return _ThumbnailBanner(message=message, is_error=False)
    return None
