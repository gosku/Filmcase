from django.urls import path

from src.interfaces.library import views

urlpatterns = [
    path("library/", views.LibraryFolderList.as_view(), name="library-list"),
    path("library/new/", views.LibraryFolderAdd.as_view(), name="library-folder-new"),
    path("library/browse/partial/", views.FilesystemBrowser.as_view(), name="library-browse"),
    path("library/<int:folder_id>/confirm-delete/", views.LibraryFolderRemoveConfirm.as_view(), name="library-folder-confirm-delete"),
    path("library/<int:folder_id>/delete/", views.LibraryFolderRemove.as_view(), name="library-folder-delete"),
    path("library/<int:folder_id>/edit/", views.LibraryFolderPathUpdate.as_view(), name="library-folder-edit"),
    path("library/<int:folder_id>/ignored/", views.LibraryFolderIgnoredImages.as_view(), name="library-folder-ignored"),
    path("library/<int:folder_id>/ignored/retry/", views.LibraryFolderIgnoredImagesRetry.as_view(), name="library-folder-ignored-retry"),
    path("library/ignored/<int:ignored_id>/retry/", views.LibraryIgnoredImageRetry.as_view(), name="library-ignored-retry"),
    path("library/<int:folder_id>/sync-status/", views.LibraryFolderSyncStatus.as_view(), name="library-folder-sync-status"),
]
