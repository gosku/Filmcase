from django.urls import path

from src.interfaces.library import views

urlpatterns = [
    path("", views.LibraryFolderList.as_view(), name="library-list"),
    path("new/", views.LibraryFolderAdd.as_view(), name="library-folder-new"),
    path("browse/partial/", views.FilesystemBrowser.as_view(), name="library-browse"),
    path("<int:folder_id>/confirm-delete/", views.LibraryFolderRemoveConfirm.as_view(), name="library-folder-confirm-delete"),
    path("<int:folder_id>/delete/", views.LibraryFolderRemove.as_view(), name="library-folder-delete"),
    path("<int:folder_id>/edit/", views.LibraryFolderPathUpdate.as_view(), name="library-folder-edit"),
    path("<int:folder_id>/ignored/", views.LibraryFolderIgnoredImages.as_view(), name="library-folder-ignored"),
    path("<int:folder_id>/ignored/retry/", views.LibraryFolderIgnoredImagesRetry.as_view(), name="library-folder-ignored-retry"),
    path("ignored/<int:ignored_id>/retry/", views.LibraryIgnoredImageRetry.as_view(), name="library-ignored-retry"),
    path("<int:folder_id>/sync-status/", views.LibraryFolderSyncStatus.as_view(), name="library-folder-sync-status"),
]
