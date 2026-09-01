import pytest

from src.domain.library.queries import (
    LibraryFolderNotFound,
    count_exclusively_owned_images,
    get_image_ids_no_longer_covered,
    get_exclusively_owned_image_ids,
    get_owning_folder,
)
from tests.factories import ImageFactory, LibraryFolderFactory


@pytest.mark.django_db
class TestGetExclusivelyOwnedImageIds:
    def test_returns_images_under_the_folder(self):
        folder = LibraryFolderFactory(path="/photos")
        image = ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == [image.pk]

    def test_excludes_images_outside_the_folder(self):
        folder = LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/elsewhere/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == []

    def test_excludes_images_a_nested_registered_folder_also_covers(self):
        outer = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")
        only_in_outer = ImageFactory(filepath="/photos/2023/DSCF0002.JPG")

        result = get_exclusively_owned_image_ids(folder_id=outer.pk)

        assert result == [only_in_outer.pk]

    def test_excludes_images_an_enclosing_registered_folder_also_covers(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=inner.pk)

        assert result == []

    def test_returns_images_when_the_only_other_folder_is_unrelated(self):
        folder = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/scans")
        image = ImageFactory(filepath="/photos/DSCF0001.JPG")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert result == [image.pk]

    def test_raises_library_folder_not_found_for_unknown_id(self):
        with pytest.raises(LibraryFolderNotFound) as exc_info:
            get_exclusively_owned_image_ids(folder_id=9999)

        assert exc_info.value.folder_id == 9999


@pytest.mark.django_db
class TestCountExclusivelyOwnedImages:
    def test_counts_only_images_no_other_folder_covers(self):
        outer = LibraryFolderFactory(path="/photos")
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")
        ImageFactory(filepath="/photos/2023/DSCF0002.JPG")

        assert count_exclusively_owned_images(folder_id=outer.pk) == 1

    def test_counts_zero_for_a_folder_fully_covered_by_another(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/DSCF0001.JPG")

        assert count_exclusively_owned_images(folder_id=inner.pk) == 0


@pytest.mark.django_db
class TestGetImageIdsNoLongerCovered:
    def test_returns_images_no_registered_folder_covers(self):
        LibraryFolderFactory(path="/photos/2024")
        stranded = ImageFactory(filepath="/photos/2023/a.jpg")

        result = get_image_ids_no_longer_covered(folder_path="/photos")

        assert result == [stranded.pk]

    def test_excludes_images_the_narrowed_folder_still_covers(self):
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2024/c.jpg")

        assert get_image_ids_no_longer_covered(folder_path="/photos") == []

    def test_excludes_images_a_second_folder_covers(self):
        LibraryFolderFactory(path="/photos/2024")
        LibraryFolderFactory(path="/photos/2023")
        ImageFactory(filepath="/photos/2023/a.jpg")

        assert get_image_ids_no_longer_covered(folder_path="/photos") == []

    def test_ignores_images_outside_the_given_path(self):
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/elsewhere/a.jpg")

        assert get_image_ids_no_longer_covered(folder_path="/photos") == []

    def test_does_not_claim_a_sibling_sharing_the_name_as_a_prefix(self):
        LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos-old/a.jpg")

        assert get_image_ids_no_longer_covered(folder_path="/photos") == []

    def test_returns_nothing_when_every_image_is_covered(self):
        LibraryFolderFactory(path="/photos")
        ImageFactory(filepath="/photos/2023/a.jpg")

        assert get_image_ids_no_longer_covered(folder_path="/photos") == []


@pytest.mark.django_db
class TestOwnershipIncludesAPreviousPath:
    def test_a_narrowed_folder_still_owns_what_its_old_path_holds(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        stranded = ImageFactory(filepath="/photos/2023/a.jpg")
        current = ImageFactory(filepath="/photos/2024/c.jpg")

        result = get_exclusively_owned_image_ids(folder_id=folder.pk)

        assert sorted(result) == sorted([stranded.pk, current.pk])

    def test_another_folder_still_wins_over_a_previous_path(self):
        folder = LibraryFolderFactory(path="/photos/2024", previous_path="/photos")
        LibraryFolderFactory(path="/photos/2023")
        ImageFactory(filepath="/photos/2023/a.jpg")

        assert get_exclusively_owned_image_ids(folder_id=folder.pk) == []

    def test_an_empty_previous_path_claims_nothing_extra(self):
        folder = LibraryFolderFactory(path="/photos/2024")
        ImageFactory(filepath="/photos/2023/a.jpg")

        assert get_exclusively_owned_image_ids(folder_id=folder.pk) == []


@pytest.mark.django_db
class TestGetOwningFolder:
    def test_returns_the_folder_a_file_sits_under(self):
        folder = LibraryFolderFactory(path="/photos")

        assert get_owning_folder(filepath="/photos/2024/DSCF0001.JPG") == folder

    def test_returns_none_when_no_folder_covers_the_file(self):
        LibraryFolderFactory(path="/photos")

        assert get_owning_folder(filepath="/elsewhere/DSCF0001.JPG") is None

    def test_returns_none_when_there_are_no_folders(self):
        assert get_owning_folder(filepath="/photos/DSCF0001.JPG") is None

    def test_the_most_specific_nested_folder_wins(self):
        LibraryFolderFactory(path="/photos")
        inner = LibraryFolderFactory(path="/photos/2024")

        assert get_owning_folder(filepath="/photos/2024/DSCF0001.JPG") == inner

    def test_does_not_claim_a_sibling_sharing_the_name_as_a_prefix(self):
        LibraryFolderFactory(path="/photos")

        assert get_owning_folder(filepath="/photos-old/DSCF0001.JPG") is None
