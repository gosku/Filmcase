import pytest

from src.data import models
from tests.factories import IgnoredImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestLibraryFolderIgnoredImages:
    def test_lists_the_folders_ignored_files(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert response.status_code == 200
        content = response.content.decode()
        assert "other_brand.jpg" in content
        assert "Not a Fujifilm photo" in content

    def test_says_nothing_was_deleted(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert "None of them has been deleted or changed" in response.content.decode()

    def test_shows_an_errors_detail(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/broken.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
            detail="OSError: disk went away",
        )

        response = client.get(f"/library/{folder.pk}/ignored/")

        content = response.content.decode()
        assert "Failed with an error" in content
        assert "OSError: disk went away" in content

    def test_filters_by_reason(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/broken.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        response = client.get(
            f"/library/{folder.pk}/ignored/?reason={models.IgnoredImage.REASON_ERROR}"
        )

        content = response.content.decode()
        assert "broken.jpg" in content
        assert "other_brand.jpg" not in content

    def test_offers_a_filter_per_reason_with_its_count(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/a.jpg")
        IgnoredImageFactory(folder=folder, filepath="/photos/b.jpg")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/c.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        response = client.get(f"/library/{folder.pk}/ignored/")

        content = response.content.decode()
        assert "Not a Fujifilm photo 2" in content
        assert "Failed with an error 1" in content

    def test_paginates(self, client, settings):
        settings.GALLERY_PAGE_SIZE = 2
        folder = LibraryFolderFactory(path="/photos")
        for index in range(5):
            IgnoredImageFactory(folder=folder, filepath=f"/photos/{index}.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        content = response.content.decode()
        assert "Page 1 of 3" in content
        assert "Next" in content

    def test_excludes_another_folders_records(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=LibraryFolderFactory(path="/scans"), filepath="/scans/x.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert "Nothing has been ignored in this folder" in response.content.decode()

    def test_returns_404_for_unknown_folder_id(self, client):
        assert client.get("/library/9999/ignored/").status_code == 404
