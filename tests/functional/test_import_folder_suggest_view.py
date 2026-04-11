import pytest
from bs4 import BeautifulSoup


@pytest.mark.django_db
class TestImportFolderSuggestView:
    def test_returns_empty_when_no_folder_param(self, client):
        response = client.get("/images/import/suggest/")

        assert response.status_code == 200
        assert response.content == b""

    def test_returns_empty_when_parent_does_not_exist(self, client):
        response = client.get("/images/import/suggest/", {"folder": "/nonexistent/path/abc"})

        assert response.status_code == 200
        assert response.content == b""

    def test_returns_subdirectories_for_existing_directory(self, client, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "gamma").mkdir()

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path) + "/"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        names = {li["data-value"].split("/")[-1] for li in soup.find_all("li")}
        assert names == {"alpha", "beta", "gamma"}

    def test_filters_suggestions_by_prefix(self, client, tmp_path):
        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "another").mkdir()

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path / "a")})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        names = {li["data-value"].split("/")[-1] for li in soup.find_all("li")}
        assert names == {"alpha", "another"}
        assert "beta" not in names

    def test_excludes_hidden_directories(self, client, tmp_path):
        (tmp_path / "visible").mkdir()
        (tmp_path / ".hidden").mkdir()

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path) + "/"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        names = {li["data-value"].split("/")[-1] for li in soup.find_all("li")}
        assert "visible" in names
        assert ".hidden" not in names

    def test_does_not_suggest_files_only_directories(self, client, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "photo.jpg").write_bytes(b"")

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path) + "/"})

        assert response.status_code == 200
        soup = BeautifulSoup(response.content, "html.parser")
        names = {li["data-value"].split("/")[-1] for li in soup.find_all("li")}
        assert names == {"subdir"}

    def test_suggestion_items_carry_data_value_attribute(self, client, tmp_path):
        (tmp_path / "photos").mkdir()

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path) + "/"})

        soup = BeautifulSoup(response.content, "html.parser")
        item = soup.find("li")
        assert item is not None
        assert item["data-value"] == str(tmp_path / "photos")

    def test_caps_results_at_fifteen(self, client, tmp_path):
        for i in range(20):
            (tmp_path / f"dir_{i:02d}").mkdir()

        response = client.get("/images/import/suggest/", {"folder": str(tmp_path) + "/"})

        soup = BeautifulSoup(response.content, "html.parser")
        assert len(soup.find_all("li")) == 15
