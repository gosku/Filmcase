from django import http, shortcuts
from django.conf import settings as django_settings
from django.forms.boundfield import BoundField
from django.views import generic

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
        return self._render(request, form)

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
    ) -> http.HttpResponse:
        return shortcuts.render(
            request,
            _TEMPLATE,
            {
                "form": form,
                "fieldsets": self._fieldsets(form),
                "saved": saved,
                "active_tab": "preferences",
            },
        )

    @staticmethod
    def _fieldsets(form: forms.Preferences) -> list[tuple[str, list[BoundField]]]:
        """
        Group the form's bound fields into the app sections declared in
        ``settings.CONSTANCE_CONFIG_FIELDSETS`` so the page mirrors the rest of
        Filmcase.
        """
        sections: list[tuple[str, list[BoundField]]] = []
        for title, keys in django_settings.CONSTANCE_CONFIG_FIELDSETS.items():
            sections.append((title, [form[key.lower()] for key in keys]))
        return sections
