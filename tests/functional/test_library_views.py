import pytest
from bs4 import BeautifulSoup

from src.data import models
from tests.factories import LibraryFolderFactory


@pytest.mark.django_db
class TestLibraryFolderList:
    def test_returns_200(self, client):
        response = client.get("/library/")
        assert response.status_code == 200

    def test_lists_all_folders(self, client, tmp_path):
        folder_a = LibraryFolderFactory(path=str(tmp_path / "a"))
        folder_b = LibraryFolderFactory(path=str(tmp_path / "b"))

        response = client.get("/library/")

        assert response.status_code == 200
        content = response.content.decode()
        assert folder_a.path in content
        assert folder_b.path in content

    def test_shows_empty_state_when_no_folders(self, client):
        response = client.get("/library/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="empty-state") is not None

    def test_shows_library_nav_link_as_active(self, client):
        response = client.get("/library/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        active_links = soup.find_all(class_="top-nav__link--active")
        assert any("Library" in link.text for link in active_links)


@pytest.mark.django_db
class TestLibraryFolderAdd:
    def test_adds_folder_and_redirects_to_list(self, client, tmp_path):
        new_dir = tmp_path / "photos"
        new_dir.mkdir()

        response = client.post("/library/new/",{"path": str(new_dir)})

        assert response.status_code == 302
        assert response["Location"] == "/library/"
        assert models.LibraryFolder.objects.filter(path=str(new_dir)).exists()

    def test_returns_error_for_nonexistent_path(self, client, tmp_path):
        missing = str(tmp_path / "does_not_exist")

        response = client.post("/library/new/",{"path": missing})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_error_for_path_already_in_library(self, client, tmp_path):
        existing_dir = tmp_path / "photos"
        existing_dir.mkdir()
        LibraryFolderFactory(path=str(existing_dir))

        response = client.post("/library/new/",{"path": str(existing_dir)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_400_when_path_is_missing(self, client):
        response = client.post("/library/new/",{})
        assert response.status_code == 400


@pytest.mark.django_db
class TestLibraryFolderRemove:
    def test_removes_folder_and_redirects_to_list(self, client):
        folder = LibraryFolderFactory()

        response = client.post(f"/library/{folder.pk}/delete/")

        assert response.status_code == 302
        assert response["Location"] == "/library/"
        assert not models.LibraryFolder.objects.filter(pk=folder.pk).exists()

    def test_returns_404_for_unknown_folder_id(self, client):
        response = client.post("/library/99999/delete/")
        assert response.status_code == 404


@pytest.mark.django_db
class TestLibraryFolderPathUpdate:
    def test_updates_path_and_redirects_to_list(self, client, tmp_path):
        old_dir = tmp_path / "old"
        new_dir = tmp_path / "new"
        old_dir.mkdir()
        new_dir.mkdir()
        folder = LibraryFolderFactory(path=str(old_dir))

        response = client.post(f"/library/{folder.pk}/edit/",{"path": str(new_dir)})

        assert response.status_code == 302
        assert response["Location"] == "/library/"
        folder.refresh_from_db()
        assert folder.path == str(new_dir)

    def test_returns_404_for_unknown_folder_id(self, client, tmp_path):
        new_dir = tmp_path / "new"
        new_dir.mkdir()

        response = client.post("/library/99999/edit/",{"path": str(new_dir)})

        assert response.status_code == 404

    def test_returns_error_for_nonexistent_path(self, client, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        missing = str(tmp_path / "does_not_exist")

        response = client.post(f"/library/{folder.pk}/edit/",{"path": missing})

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

        response = client.post(f"/library/{folder_b.pk}/edit/",{"path": str(dir_a)})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="error-banner") is not None

    def test_returns_400_when_path_is_missing(self, client):
        folder = LibraryFolderFactory()

        response = client.post(f"/library/{folder.pk}/edit/",{})

        assert response.status_code == 400


@pytest.mark.django_db
class TestFilesystemBrowser:
    def test_returns_200_with_default_path(self, client):
        response = client.get("/library/browse/partial/")
        assert response.status_code == 200

    def test_lists_immediate_subdirectories(self, client, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()

        response = client.get(f"/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        content = response.content.decode()
        assert "alpha" in content
        assert "beta" in content

    def test_shows_back_link_when_not_at_root(self, client, tmp_path):
        response = client.get(f"/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="browser-back-link") is not None

    def test_no_back_link_at_filesystem_root(self, client):
        response = client.get("/library/browse/partial/?path=/")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="browser-back-link") is None

    def test_returns_404_for_nonexistent_path(self, client, tmp_path):
        missing = str(tmp_path / "does_not_exist")

        response = client.get(f"/library/browse/partial/?path={missing}")

        assert response.status_code == 404

    def test_select_form_posts_to_add_url_without_folder_id(self, client, tmp_path):
        response = client.get(f"/library/browse/partial/?path={tmp_path}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        assert form["action"] == "/library/new/"

    def test_select_form_posts_to_update_url_with_folder_id(self, client, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        response = client.get(f"/library/browse/partial/?path={tmp_path}&folder_id={folder.pk}")

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find("form")
        assert form["action"] == f"/library/{folder.pk}/edit/"

    def test_returns_400_for_non_integer_folder_id(self, client, tmp_path):
        response = client.get(f"/library/browse/partial/?path={tmp_path}&folder_id=not-an-int")

        assert response.status_code == 400
