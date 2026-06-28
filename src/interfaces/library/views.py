from django import http, shortcuts, urls
from django.views import generic

from src.application.usecases.library import add_library_folder as add_library_folder_uc
from src.application.usecases.library import browse_filesystem as browse_filesystem_uc
from src.application.usecases.library import dataclasses as library_dataclasses
from src.application.usecases.library import remove_library_folder as remove_library_folder_uc
from src.application.usecases.library import update_library_folder_path as update_library_folder_path_uc
from src.data import models
from src.domain.library import queries as domain_queries


def _folder_data(folder: models.LibraryFolder) -> library_dataclasses.LibraryFolderData:
    return library_dataclasses.LibraryFolderData(
        folder_id=folder.pk,
        path=folder.path,
        created_at=folder.created_at,
        last_processed_at=folder.last_processed_at,
        last_checked_at=folder.last_checked_at,
    )


def _list_all_folders() -> list[library_dataclasses.LibraryFolderData]:
    return [_folder_data(f) for f in domain_queries.get_all_library_folders()]


class LibraryFolderList(generic.View):
    """Display the list of monitored library folders."""

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        return shortcuts.render(request, "library/library.html", {"folders": _list_all_folders()})


class LibraryFolderAdd(generic.View):
    """Add a new folder to the image library."""

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        path = request.POST.get("path", "").strip()
        if not path:
            return http.HttpResponseBadRequest("path is required")
        try:
            add_library_folder_uc.add_library_folder(path=path)
        except add_library_folder_uc.FolderNotFound as exc:
            return shortcuts.render(request, "library/library.html", {
                "folders": _list_all_folders(),
                "error": f"Folder does not exist: {exc.path}",
            })
        except add_library_folder_uc.FolderAlreadyInLibrary as exc:
            return shortcuts.render(request, "library/library.html", {
                "folders": _list_all_folders(),
                "error": f"Folder is already in the library: {exc.path}",
            })
        return shortcuts.redirect(urls.reverse("library-list"))


class LibraryFolderRemove(generic.View):
    """Remove a folder from the image library.

    :raises Http404: if no folder with the given ID exists.
    """

    def post(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        try:
            remove_library_folder_uc.remove_library_folder(folder_id=folder_id)
        except remove_library_folder_uc.LibraryFolderNotFound:
            raise http.Http404
        return shortcuts.redirect(urls.reverse("library-list"))


class LibraryFolderPathUpdate(generic.View):
    """Update the path of a library folder.

    :raises Http404: if no folder with the given ID exists.
    """

    def post(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        path = request.POST.get("path", "").strip()
        if not path:
            return http.HttpResponseBadRequest("path is required")
        try:
            update_library_folder_path_uc.update_library_folder_path(folder_id=folder_id, path=path)
        except update_library_folder_path_uc.LibraryFolderNotFound:
            raise http.Http404
        except update_library_folder_path_uc.FolderNotFound as exc:
            return shortcuts.render(request, "library/library.html", {
                "folders": _list_all_folders(),
                "error": f"Folder does not exist: {exc.path}",
            })
        except update_library_folder_path_uc.FolderAlreadyInLibrary as exc:
            return shortcuts.render(request, "library/library.html", {
                "folders": _list_all_folders(),
                "error": f"Folder is already in the library: {exc.path}",
            })
        return shortcuts.redirect(urls.reverse("library-list"))


class FilesystemBrowser(generic.View):
    """Return an HTMX partial for the filesystem browser.

    Query params:
    - path: directory to list (defaults to home directory)
    - folder_id: when set, the select form posts to the update URL instead of add

    :raises Http404: if path does not exist or is not a directory.
    """

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        path = request.GET.get("path", "")
        folder_id_raw = request.GET.get("folder_id")
        try:
            folder_id: int | None = int(folder_id_raw) if folder_id_raw else None
        except ValueError:
            return http.HttpResponseBadRequest("folder_id must be an integer")

        try:
            result = browse_filesystem_uc.browse_filesystem(path=path)
        except browse_filesystem_uc.FolderNotFound:
            raise http.Http404

        if folder_id is not None:
            action_url = urls.reverse("library-folder-edit", kwargs={"folder_id": folder_id})
        else:
            action_url = urls.reverse("library-folder-new")

        return shortcuts.render(request, "library/partials/filesystem_browser.html", {
            "result": result,
            "action_url": action_url,
            "folder_id": folder_id,
        })
