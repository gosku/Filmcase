import pytest

from src.application.usecases.images.remove_images import remove_images_from_gallery
from src.data import models
from tests.factories import ImageFactory, LibraryFolderFactory


def _photo(*, folder_path, name, content=b"\xff\xd8abc"):
    path = folder_path / name
    path.write_bytes(content)
    return path


@pytest.mark.django_db
class TestRemoveImagesFromGallery:
    def test_removes_and_ignores_an_image_under_a_folder(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        result = remove_images_from_gallery(image_ids=[image.pk])

        assert result.removed_count == 1
        assert result.ignored_count == 1
        assert result.not_found_count == 0
        assert result.all_succeeded is True
        assert not models.Image.objects.filter(pk=image.pk).exists()
        ignored = models.IgnoredImage.objects.get(filepath=str(photo))
        assert ignored.reason == models.IgnoredImage.REASON_USER_REMOVED
        assert ignored.folder_id == folder.pk

    def test_keeps_the_file_on_disk(self, tmp_path):
        LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        remove_images_from_gallery(image_ids=[image.pk])

        assert photo.exists()

    def test_removes_without_ignoring_an_image_under_no_folder(self, tmp_path):
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        result = remove_images_from_gallery(image_ids=[image.pk])

        assert result.removed_count == 1
        assert result.ignored_count == 0
        assert not models.Image.objects.filter(pk=image.pk).exists()
        assert not models.IgnoredImage.objects.filter(filepath=str(photo)).exists()

    def test_removes_without_ignoring_when_the_file_is_gone_from_disk(self, tmp_path):
        LibraryFolderFactory(path=str(tmp_path))
        image = ImageFactory(filepath=str(tmp_path / "missing.jpg"))

        result = remove_images_from_gallery(image_ids=[image.pk])

        assert result.removed_count == 1
        assert result.ignored_count == 0
        assert not models.Image.objects.filter(pk=image.pk).exists()
        assert not models.IgnoredImage.objects.filter(filepath=image.filepath).exists()

    def test_counts_an_unknown_id_as_not_found(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path, name="a.jpg")
        image = ImageFactory(filepath=str(photo))

        result = remove_images_from_gallery(image_ids=[image.pk, 9999])

        assert result.requested_count == 2
        assert result.removed_count == 1
        assert result.not_found_count == 1
        assert result.all_succeeded is False
        assert folder  # the surviving folder still exists

    def test_removes_a_mix_of_covered_and_uncovered_images(self, tmp_path):
        LibraryFolderFactory(path=str(tmp_path))
        covered = ImageFactory(filepath=str(_photo(folder_path=tmp_path, name="a.jpg")))
        uncovered_dir = tmp_path.parent / "outside"
        uncovered_dir.mkdir()
        uncovered = ImageFactory(filepath=str(_photo(folder_path=uncovered_dir, name="b.jpg")))

        result = remove_images_from_gallery(image_ids=[covered.pk, uncovered.pk])

        assert result.removed_count == 2
        assert result.ignored_count == 1
