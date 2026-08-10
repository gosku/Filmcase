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


@pytest.mark.django_db
class TestRetryingIgnoredImages:
    def test_per_row_retry_forgets_that_file(self, client):
        folder = LibraryFolderFactory(path="/photos")
        ignored = IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")

        response = client.post(f"/library/ignored/{ignored.pk}/retry/")

        assert response.status_code == 302
        assert models.IgnoredImage.objects.count() == 0

    def test_per_row_retry_returns_to_the_page_it_came_from(self, client):
        folder = LibraryFolderFactory(path="/photos")
        ignored = IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")
        came_from = f"/library/{folder.pk}/ignored/?page=2"

        response = client.post(f"/library/ignored/{ignored.pk}/retry/", {"next": came_from})

        assert response["Location"] == came_from

    def test_per_row_retry_returns_404_for_unknown_id(self, client):
        assert client.post("/library/ignored/9999/retry/").status_code == 404

    def test_retry_all_errors_leaves_the_other_reasons_alone(self, client):
        folder = LibraryFolderFactory(path="/photos")
        kept = IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/broken.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        client.post(
            f"/library/{folder.pk}/ignored/retry/",
            {"reason": models.IgnoredImage.REASON_ERROR},
        )

        assert list(models.IgnoredImage.objects.values_list("pk", flat=True)) == [kept.pk]

    def test_retry_everything_forgets_the_whole_folder(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/a.jpg")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/b.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        response = client.post(f"/library/{folder.pk}/ignored/retry/")

        assert response.status_code == 302
        assert models.IgnoredImage.objects.count() == 0

    def test_bulk_retry_returns_404_for_unknown_folder(self, client):
        assert client.post("/library/9999/ignored/retry/").status_code == 404

    def test_offers_retry_all_errors_only_when_there_are_errors(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert "Retry all" not in response.content.decode()

    def test_warns_that_retrying_a_rejected_file_does_nothing_until_it_changes(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(folder=folder, filepath="/photos/other_brand.jpg")

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert "Only changes anything once the file itself has changed" in response.content.decode()

    def test_does_not_warn_on_an_error_row(self, client):
        folder = LibraryFolderFactory(path="/photos")
        IgnoredImageFactory(
            folder=folder,
            filepath="/photos/broken.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        response = client.get(f"/library/{folder.pk}/ignored/")

        assert "Only changes anything once" not in response.content.decode()
