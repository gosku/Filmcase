import os

from django import http, shortcuts, urls
from django.conf import settings
from django.core import paginator as django_paginator
from django.views import generic

from src.application.usecases.library import add_library_folder as add_library_folder_uc
from src.application.usecases.library import browse_filesystem as browse_filesystem_uc
from src.application.usecases.library import dataclasses as library_dataclasses
from src.application.usecases.library import get_folder_removal_preview as get_folder_removal_preview_uc
from src.application.usecases.library import remove_library_folder as remove_library_folder_uc
from src.application.usecases.library import retry_ignored_images as retry_ignored_images_uc
from src.application.usecases.library import trigger_folder_sync as trigger_folder_sync_uc
from src.application.usecases.library import update_library_folder_path as update_library_folder_path_uc
from src.data import models
from src.domain.library import queries as domain_queries


def _folder_data(
    folder: models.LibraryFolder,
    ignored_count: int = 0,
) -> library_dataclasses.LibraryFolderData:
    return library_dataclasses.LibraryFolderData(
        folder_id=folder.pk,
        path=folder.path,
        created_at=folder.created_at,
        last_processed_at=folder.last_processed_at,
        last_checked_at=folder.last_checked_at,
        ignored_count=ignored_count,
    )


def _list_all_folders() -> list[library_dataclasses.LibraryFolderData]:
    # One aggregate for every folder, rather than a count query per row.
    counts = domain_queries.get_ignored_counts_by_folder()
    return [
        _folder_data(folder, ignored_count=counts.get(folder.pk, 0))
        for folder in domain_queries.get_all_library_folders()
    ]


def _render_library_list(request: http.HttpRequest, *, error: str | None = None) -> http.HttpResponse:
    context: dict[str, object] = {"folders": _list_all_folders(), "active_tab": "library"}
    if error is not None:
        context["error"] = error
    return shortcuts.render(request, "library/library.html", context)


def _sync_status(run: models.SyncRun) -> library_dataclasses.SyncRunData:
    total = run.total
    handled = run.processed + run.skipped + run.errors
    percent = int(handled / total * 100) if total else 0
    return library_dataclasses.SyncRunData(
        folder_id=run.folder_id,
        total=total,
        processed=run.processed,
        skipped=run.skipped,
        errors=run.errors,
        handled=handled,
        percent=percent,
        removed=run.removed,
        missing_found=run.missing_found,
        uncovered_found=run.uncovered_found,
        is_active=run.state in models.SyncRun.ACTIVE_STATES,
        is_scanning=run.state == models.SyncRun.STATE_SCANNING,
        is_processing=run.state == models.SyncRun.STATE_PROCESSING,
        is_pruning=run.state == models.SyncRun.STATE_PRUNING,
        is_completed=run.state == models.SyncRun.STATE_COMPLETED,
        is_failed=run.state == models.SyncRun.STATE_FAILED,
        is_interrupted=run.state == models.SyncRun.STATE_INTERRUPTED,
        folder_is_missing=run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING,
        prune_skipped_by_guard=run.prune_skipped == models.SyncRun.SKIPPED_GUARD,
    )


class LibraryFolderList(generic.View):
    """Display the list of monitored library folders."""

    def get(self, request: http.HttpRequest) -> http.HttpResponse:
        return _render_library_list(request)


class LibraryFolderAdd(generic.View):
    """Add a new folder to the image library."""

    def post(self, request: http.HttpRequest) -> http.HttpResponse:
        path = request.POST.get("path", "").strip()
        if not path:
            return http.HttpResponseBadRequest("path is required")
        try:
            folder = add_library_folder_uc.add_library_folder(path=path)
        except add_library_folder_uc.FolderNotFound as exc:
            return _render_library_list(request, error=f"Folder does not exist: {exc.path}")
        except add_library_folder_uc.FolderAlreadyInLibrary as exc:
            return _render_library_list(request, error=f"Folder is already in the library: {exc.path}")

        try:
            trigger_folder_sync_uc.trigger_folder_sync(folder_id=folder.folder_id)
        except trigger_folder_sync_uc.CeleryWorkerUnavailable:
            return _render_library_list(
                request,
                error="Folder added, but no image worker is running to sync it. Start one with 'make worker'.",
            )
        return shortcuts.redirect(urls.reverse("library-list"))


class LibraryFolderRemoveConfirm(generic.View):
    """Show what removing a folder would cost before anything happens.

    :raises Http404: if no folder with the given ID exists.
    """

    def get(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        try:
            preview = get_folder_removal_preview_uc.get_folder_removal_preview(folder_id=folder_id)
        except get_folder_removal_preview_uc.LibraryFolderNotFound:
            raise http.Http404
        return shortcuts.render(request, "library/partials/remove_folder_confirm.html", {
            "preview": preview,
        })


class LibraryFolderRemove(generic.View):
    """Remove a folder from the image library, optionally with its images.

    :raises Http404: if no folder with the given ID exists.
    """

    def post(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        delete_images = request.POST.get("delete_images") == "on"
        try:
            remove_library_folder_uc.remove_library_folder(
                folder_id=folder_id,
                delete_images=delete_images,
            )
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
            return _render_library_list(request, error=f"Folder does not exist: {exc.path}")
        except update_library_folder_path_uc.FolderAlreadyInLibrary as exc:
            return _render_library_list(request, error=f"Folder is already in the library: {exc.path}")

        try:
            trigger_folder_sync_uc.trigger_folder_sync(folder_id=folder_id)
        except trigger_folder_sync_uc.CeleryWorkerUnavailable:
            return _render_library_list(
                request,
                error="Path updated, but no image worker is running to sync it. Start one with 'make worker'.",
            )
        return shortcuts.redirect(urls.reverse("library-list"))


class LibraryFolderSyncStatus(generic.View):
    """Return an HTMX partial with the latest sync-run status for a folder."""

    def get(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        run = domain_queries.get_latest_sync_run(folder_id=folder_id)
        status = _sync_status(run) if run is not None else None
        return shortcuts.render(request, "library/partials/sync_status.html", {
            "status": status,
            "folder_id": folder_id,
        })


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


_IGNORED_REASON_LABELS = {
    models.IgnoredImage.REASON_NO_FILM_SIMULATION: "Not a Fujifilm photo",
    models.IgnoredImage.REASON_INVALID_RECIPE_DATA: "Recipe could not be read",
    models.IgnoredImage.REASON_ERROR: "Failed with an error",
}
# Only an error is worth retrying by hand. The other two are verdicts on the
# file's own contents, so an unchanged file gets the same verdict again.
_RETRY_CHANGES_SOMETHING = {models.IgnoredImage.REASON_ERROR}


def _ignored_image_data(ignored: models.IgnoredImage) -> library_dataclasses.IgnoredImageData:
    return library_dataclasses.IgnoredImageData(
        ignored_id=ignored.pk,
        filepath=ignored.filepath,
        filename=os.path.basename(ignored.filepath),
        reason_label=_IGNORED_REASON_LABELS.get(ignored.reason, ignored.reason),
        detail=ignored.detail,
        created_at=ignored.created_at,
        retry_is_a_no_op_until_the_file_changes=ignored.reason not in _RETRY_CHANGES_SOMETHING,
    )


def _reason_filters(*, counts: dict[str, int], active: str | None) -> list[library_dataclasses.IgnoredReasonFilter]:
    return [
        library_dataclasses.IgnoredReasonFilter(
            code=code,
            label=label,
            count=counts.get(code, 0),
            is_active=active == code,
        )
        for code, label in _IGNORED_REASON_LABELS.items()
        if counts.get(code, 0)
    ]


class LibraryFolderIgnoredImages(generic.View):
    """List the files this folder's syncs could not import.

    :raises Http404: if no folder with the given ID exists.
    """

    def get(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        try:
            folder = domain_queries.get_library_folder(folder_id=folder_id)
        except domain_queries.LibraryFolderNotFound:
            raise http.Http404

        reason = request.GET.get("reason") or None
        ignored = domain_queries.get_ignored_images(folder_id=folder_id, reason=reason)
        counts = domain_queries.count_ignored_images_by_reason(folder_id=folder_id)
        page_obj = django_paginator.Paginator(ignored, settings.GALLERY_PAGE_SIZE).get_page(
            request.GET.get("page", 1)
        )

        return shortcuts.render(request, "library/ignored_images.html", {
            "active_tab": "library",
            "folder": _folder_data(folder),
            "ignored_images": [_ignored_image_data(i) for i in page_obj],
            "page_obj": page_obj,
            "reason_filters": _reason_filters(counts=counts, active=reason),
            "active_reason": reason,
            "total": sum(counts.values()),
            "error_count": counts.get(models.IgnoredImage.REASON_ERROR, 0),
            "error_reason_code": models.IgnoredImage.REASON_ERROR,
        })


class LibraryIgnoredImageRetry(generic.View):
    """Forget one ignored file so the next sync examines it again.

    :raises Http404: if no ignored-image record with the given ID exists.
    """

    def post(self, request: http.HttpRequest, ignored_id: int) -> http.HttpResponse:
        try:
            retry_ignored_images_uc.retry_ignored_image(ignored_id=ignored_id)
        except retry_ignored_images_uc.IgnoredImageNotFound:
            raise http.Http404
        return shortcuts.redirect(request.POST.get("next") or urls.reverse("library-list"))


class LibraryFolderIgnoredImagesRetry(generic.View):
    """Forget what a folder has ignored, optionally only one reason.

    :raises Http404: if no folder with the given ID exists.
    """

    def post(self, request: http.HttpRequest, folder_id: int) -> http.HttpResponse:
        reason = request.POST.get("reason") or None
        try:
            retry_ignored_images_uc.retry_ignored_images(folder_id=folder_id, reason=reason)
        except retry_ignored_images_uc.LibraryFolderNotFound:
            raise http.Http404
        return shortcuts.redirect(urls.reverse("library-folder-ignored", args=[folder_id]))
