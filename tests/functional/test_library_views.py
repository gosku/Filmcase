from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup

from src.application.usecases.library.trigger_folder_sync import CeleryWorkerUnavailable
from src.data import models
from tests.factories import IgnoredImageFactory, ImageFactory, LibraryFolderFactory

TRIGGER = "src.interfaces.library.views.trigger_folder_sync_uc.trigger_folder_sync"


@pytest.mark.django_db
class TestLibraryFolderList:
    def test_returns_200(self, client):
        response = client.get("/settings/library/")
        assert response.status_code == 200

    def test_lists_all_folders(self, client, tmp_path):
        folder_a = LibraryFolderFactory(path=str(tmp_path / "a"))
        folder_b = LibraryFolderFactory(path=str(tmp_path / "b"))

        response = client.get("/settings/library/")

        assert response.status_code == 200
        content = response.content.decode()
        assert folder_a.path in content
        assert folder_b.path in content

    def test_shows_empty_state_when_no_folders(self, client):
        response = client.get("/settings/library/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="empty-state") is not None

    def test_folder_row_lazy_loads_its_sync_status(self, client, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        response = client.get("/settings/library/")

        content = response.content.decode()
        assert f"/settings/library/{folder.pk}/sync-status/" in content
        assert 'hx-trigger="load"' in content

    def test_shows_library_nav_link_as_active(self, client):
        response = client.get("/settings/library/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        active_links = soup.find_all(class_="top-nav__link--active")
        assert any("Library" in link.text for link in active_links)


@pytest.mark.django_db
class TestLibraryFolderAdd:
    def test_adds_folder_and_redirects_to_list(self, client, tmp_path):
        new_dir = tmp_path / "photos"
        new_dir.mkdir()

        with patch(TRIGGER):
            response = client.post("/settings/library/new/",{"path": str(new_dir)})

        assert response.status_code == 302
        assert response["Location"] == "/settings/library/"
        assert models.LibraryFolder.objects.filter(path=str(new_dir)).exists()

    def test_triggers_sync_for_the_new_folder(self, client, tmp_path):
        new_dir = tmp_path / "photos"
        new_dir.mkdir()

        with patch(TRIGGER) as mock_trigger:
            client.post("/settings/library/new/",{"path": str(new_dir)})

        folder = models.LibraryFolder.objects.get(path=str(new_dir))
        mock_trigger.assert_called_once_with(folder_id=folder.pk)

    def test_shows_error_when_worker_unavailable_on_add(self, client, tmp_path):
        new_dir = tmp_path / "photos"
        new_dir.mkdir()

        with patch(TRIGGER, side_effect=CeleryWorkerUnavailable()):
            response = client.post("/settings/library/new/",{"path": str(new_dir)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None
        # The folder is still registered even though the sync could not start.
        assert models.LibraryFolder.objects.filter(path=str(new_dir)).exists()

    def test_returns_error_for_nonexistent_path(self, client, tmp_path):
        missing = str(tmp_path / "does_not_exist")

        response = client.post("/settings/library/new/",{"path": missing})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_error_for_path_already_in_library(self, client, tmp_path):
        existing_dir = tmp_path / "photos"
        existing_dir.mkdir()
        LibraryFolderFactory(path=str(existing_dir))

        response = client.post("/settings/library/new/",{"path": str(existing_dir)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_400_when_path_is_missing(self, client):
        response = client.post("/settings/library/new/",{})
        assert response.status_code == 400


@pytest.mark.django_db
class TestLibraryFolderRemove:
    def test_removes_folder_and_redirects_to_list(self, client):
        folder = LibraryFolderFactory()

        response = client.post(f"/settings/library/{folder.pk}/delete/")

        assert response.status_code == 302
        assert response["Location"] == "/settings/library/"
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_returns_404_for_unknown_folder_id(self, client):
        response = client.post("/settings/library/99999/delete/")
        assert response.status_code == 404

    def test_keeps_the_images_by_default(self, client):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        client.post(f"/settings/library/{folder.pk}/delete/")

        assert models.Image.objects.filter(pk=image.pk).exists()

    def test_removes_the_images_when_asked_to(self, client):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        client.post(f"/settings/library/{folder.pk}/delete/", {"delete_images": "on"})

        assert not models.Image.objects.filter(pk=image.pk).exists()


@pytest.mark.django_db
class TestLibraryFolderRemoveConfirm:
    def test_shows_how_many_images_would_leave_the_gallery(self, client):
        folder = LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/photos/DSCF0001.JPG")
        ImageFactory(filepath="/photos/2024/DSCF0002.JPG")

        response = client.get(f"/settings/library/{folder.pk}/confirm-delete/")

        content = response.content.decode()
        assert response.status_code == 200
        assert "2" in content
        assert "Remove folder and its 2 images from the gallery" in content

    def test_says_the_files_stay_on_disk(self, client):
        folder = LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/photos/DSCF0001.JPG")

        response = client.get(f"/settings/library/{folder.pk}/confirm-delete/")

        assert "Your photo files are never deleted" in response.content.decode()

    def test_offers_only_the_folder_when_nothing_would_leave_the_gallery(self, client):
        folder = LibraryFolderFactory(path="/photos")

        response = client.get(f"/settings/library/{folder.pk}/confirm-delete/")

        content = response.content.decode()
        assert "No image in the gallery comes only from this folder" in content
        assert "delete_images" not in content

    def test_reports_nothing_removable_for_a_folder_nested_in_another(self, client):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        response = client.get(f"/settings/library/{inner.pk}/confirm-delete/")

        assert "No image in the gallery comes only from this folder" in response.content.decode()

    def test_returns_404_for_unknown_folder_id(self, client):
        assert client.get("/settings/library/99999/confirm-delete/").status_code == 404


@pytest.mark.django_db
class TestLibraryFolderPathUpdate:
    def test_updates_path_and_redirects_to_list(self, client, tmp_path):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()
        folder = LibraryFolderFactory(path=str(old_dir))

        with patch(TRIGGER):
            response = client.post(f"/settings/library/{folder.pk}/edit/",{"path": str(new_dir)})

        assert response.status_code == 302
        assert response["Location"] == "/settings/library/"
        folder.refresh_from_db()
        assert folder.path == str(new_dir)

    def test_triggers_sync_after_path_update(self, client, tmp_path):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()
        folder = LibraryFolderFactory(path=str(old_dir))

        with patch(TRIGGER) as mock_trigger:
            client.post(f"/settings/library/{folder.pk}/edit/",{"path": str(new_dir)})

        mock_trigger.assert_called_once_with(folder_id=folder.pk)

    def test_returns_404_for_unknown_folder_id(self, client, tmp_path):
        new_dir = tmp_path / "new"
        new_dir.mkdir()

        response = client.post("/settings/library/99999/edit/",{"path": str(new_dir)})

        assert response.status_code == 404

    def test_returns_error_for_nonexistent_path(self, client, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        missing = str(tmp_path / "does_not_exist")

        response = client.post(f"/settings/library/{folder.pk}/edit/",{"path": missing})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_error_when_path_taken_by_another_folder(self, client, tmp_path):
        dir_a = tmp_path / "a"
        dir_b = tmp_path / "b"
        dir_a.mkdir()
        dir_b.mkdir()
        LibraryFolderFactory(path=str(dir_a))
        folder_b = LibraryFolderFactory(path=str(dir_b))

        response = client.post(f"/settings/library/{folder_b.pk}/edit/",{"path": str(dir_a)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_400_when_path_is_missing(self, client):
        folder = LibraryFolderFactory()

        response = client.post(f"/settings/library/{folder.pk}/edit/",{})

        assert response.status_code == 400


@pytest.mark.django_db
class TestFilesystemBrowser:
    def test_returns_200_with_default_path(self, client):
        response = client.get("/settings/library/browse/partial/")
        assert response.status_code == 200

    def test_lists_immediate_subdirectories(self, client, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()

        response = client.get(f"/settings/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        content = response.content.decode()
        assert "alpha" in content
        assert "beta" in content

    def test_shows_back_link_when_not_at_root(self, client, tmp_path):
        response = client.get(f"/settings/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="browser-back-link") is not None

    def test_no_back_link_at_filesystem_root(self, client):
        response = client.get("/settings/library/browse/partial/?path=/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="browser-back-link") is None

    def test_returns_404_for_nonexistent_path(self, client, tmp_path):
        missing = str(tmp_path / "does_not_exist")

        response = client.get(f"/settings/library/browse/partial/?path={missing}")

        assert response.status_code == 404

    def test_select_form_posts_to_add_url_without_folder_id(self, client, tmp_path):
        response = client.get(f"/settings/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        assert form["action"] == "/settings/library/new/"

    def test_select_form_posts_to_update_url_with_folder_id(self, client, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        response = client.get(f"/settings/library/browse/partial/?path={tmp_path}&folder_id={folder.pk}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        assert form["action"] == f"/settings/library/{folder.pk}/edit/"

    def test_returns_400_for_non_integer_folder_id(self, client, tmp_path):
        response = client.get(f"/settings/library/browse/partial/?path={tmp_path}&folder_id=not-an-int")

        assert response.status_code == 400


@pytest.mark.django_db
class TestLibraryPageIgnoredCount:
    def test_links_to_the_ignored_page_with_the_count(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/a.jpg")
        IgnoredImageFactory(folder=folder, filepath="/photos/b.jpg")

        response = client.get("/settings/library/")

        content = response.content.decode()
        assert "2 ignored" in content
        assert f"/settings/library/{folder.pk}/ignored/" in content

    def test_shows_none_without_a_link_when_nothing_is_ignored(self, client):
        folder = LibraryFolderFactory(path="/photos")

        response = client.get("/settings/library/")

        content = response.content.decode()
        assert f"/settings/library/{folder.pk}/ignored/" not in content
        assert "None" in content

    def test_counts_each_folder_separately(self, client):
        first = LibraryFolderFactory(path="/photos")
        second = LibraryFolderFactory(path="/scans")
        IgnoredImageFactory(folder=first, filepath="/photos/a.jpg")
        IgnoredImageFactory(folder=second, filepath="/scans/a.jpg")
        IgnoredImageFactory(folder=second, filepath="/scans/b.jpg")

        content = client.get("/settings/library/").content.decode()

        assert "1 ignored" in content
        assert "2 ignored" in content
