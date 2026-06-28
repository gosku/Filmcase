from django.urls import path

from src.interfaces.library import views

urlpatterns = [
    path("library/", views.LibraryFolderList.as_view(), name="library-list"),
    path("library/new/", views.LibraryFolderAdd.as_view(), name="library-folder-new"),
    path("library/browse/partial/", views.FilesystemBrowser.as_view(), name="library-browse"),
    path("library/<int:folder_id>/delete/", views.LibraryFolderRemove.as_view(), name="library-folder-delete"),
    path("library/<int:folder_id>/edit/", views.LibraryFolderPathUpdate.as_view(), name="library-folder-edit"),
]
