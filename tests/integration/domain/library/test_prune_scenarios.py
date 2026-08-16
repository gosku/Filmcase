"""
One test per row of the scenario matrix in ADR 013.

Each test builds a real tree of JPEGs, imports it through the ordinary sync, then
mutates the filesystem exactly as the scenario describes and syncs again. Test
names carry the scenario number so the matrix and this suite stay tied together.

Two invariants run through all of them: user data (rating, favourite, album)
survives a move, and no image file is ever deleted from disk.
"""

import shutil
from pathlib import Path

import pytest

from src.application.usecases.library.sync_folder import sync_folder
from src.application.usecases.library.sync_library import sync_library
from src.data import models
from src.domain.library.operations import remove_library_folder, update_library_folder_path
from src.domain.images.operations import process_image
from tests.factories import LibraryFolderFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FIXTURE_A = FIXTURES_DIR / "XS107114.JPG"
FIXTURE_B = FIXTURES_DIR / "XS107209.jpg"
FIXTURE_C = FIXTURES_DIR / "XS107336.jpg"

pytestmark = pytest.mark.django_db


def _place(*, fixture: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(fixture, destination)
    return destination


def _catalogued() -> set[str]:
    return set(models.Image.objects.values_list("filepath", flat=True))


@pytest.fixture(autouse=True)
def _lite_mode_with_a_generous_guard(settings):
    # Run everything inline so a sync is finished, prune included, when it
    # returns. These trees are tiny, so the guard is held off; it has its own tests.
    settings.USE_ASYNC_TASKS = False
    settings.LIBRARY_PRUNE_GUARD_MIN_IMAGES = 1000


class TestFileLevelScenarios:
    def test_01_a_deleted_file_leaves_the_gallery(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        assert models.Image.objects.count() == 1

        photo.unlink()
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 0

    def test_02_a_file_renamed_in_place_is_relocated(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        image = models.Image.objects.get()
        image.set_rating(4)
        image.set_as_favorite()

        renamed = tmp_path / "spain.JPG"
        photo.rename(renamed)
        sync_folder(folder_id=folder.pk)

        image.refresh_from_db()
        assert models.Image.objects.count() == 1
        assert image.filepath == str(renamed)
        assert image.filename == "spain.JPG"
        assert image.rating == 4
        assert image.is_favorite is True
        assert renamed.exists()

    def test_03_a_file_moved_into_a_subfolder_is_relocated(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        image = models.Image.objects.get()
        image.set_rating(3)

        moved = tmp_path / "2025" / "DSCF0001.JPG"
        moved.parent.mkdir()
        photo.rename(moved)
        sync_folder(folder_id=folder.pk)

        image.refresh_from_db()
        assert models.Image.objects.count() == 1
        assert image.filepath == str(moved)
        assert image.rating == 3

    def test_04_a_file_moved_between_tracked_folders_is_relocated(self, tmp_path):
        source_dir = tmp_path / "inbox"
        target_dir = tmp_path / "keepers"
        source_dir.mkdir()
        target_dir.mkdir()
        LibraryFolderFactory(path=str(source_dir))
        LibraryFolderFactory(path=str(target_dir))
        photo = _place(fixture=FIXTURE_A, destination=source_dir / "DSCF0001.JPG")
        sync_library()
        image = models.Image.objects.get()
        image.set_rating(5)

        moved = target_dir / "DSCF0001.JPG"
        photo.rename(moved)
        sync_library()

        image.refresh_from_db()
        assert models.Image.objects.count() == 1
        assert image.filepath == str(moved)
        assert image.rating == 5

    def test_05_a_file_moved_outside_every_tracked_folder_leaves_the_gallery(self, tmp_path):
        library_dir = tmp_path / "library"
        outside_dir = tmp_path / "outside"
        library_dir.mkdir()
        outside_dir.mkdir()
        folder = LibraryFolderFactory(path=str(library_dir))
        photo = _place(fixture=FIXTURE_A, destination=library_dir / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        moved = outside_dir / "DSCF0001.JPG"
        photo.rename(moved)
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 0
        assert moved.exists()

    def test_06_a_copy_alongside_the_original_adds_nothing(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        original = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        _place(fixture=FIXTURE_A, destination=tmp_path / "backup" / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 1
        assert models.Image.objects.get().filepath == str(original)

    def test_07_a_copy_kept_after_the_original_goes_is_re_imported(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        original = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        copy = _place(fixture=FIXTURE_A, destination=tmp_path / "backup" / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        original.unlink()
        sync_folder(folder_id=folder.pk)

        # Self-healing but lossy: the record went with the original and the copy
        # comes back as a fresh import on the next pass. See ADR 013, risk 3.
        assert _catalogued() == {str(copy)}

    def test_08_a_file_edited_in_place_keeps_its_record(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        image = models.Image.objects.get()

        shutil.copy(FIXTURE_B, photo)
        sync_folder(folder_id=folder.pk)

        image.refresh_from_db()
        assert models.Image.objects.count() == 1
        assert image.filepath == str(photo)


class TestDirectoryLevelScenarios:
    def test_09_a_deleted_subfolder_takes_its_images_out_of_the_gallery(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        subdir = tmp_path / "2024"
        _place(fixture=FIXTURE_A, destination=subdir / "DSCF0001.JPG")
        _place(fixture=FIXTURE_B, destination=subdir / "DSCF0002.jpg")
        kept = _place(fixture=FIXTURE_C, destination=tmp_path / "2025" / "DSCF0003.jpg")
        sync_folder(folder_id=folder.pk)
        assert models.Image.objects.count() == 3

        shutil.rmtree(subdir)
        sync_folder(folder_id=folder.pk)

        assert _catalogued() == {str(kept)}

    def test_10_a_subfolder_moved_out_of_the_tree_takes_its_images(self, tmp_path):
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        folder = LibraryFolderFactory(path=str(library_dir))
        subdir = library_dir / "2024"
        _place(fixture=FIXTURE_A, destination=subdir / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        subdir.rename(tmp_path / "2024")
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 0

    def test_11_a_renamed_subfolder_relocates_every_image_under_it(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        subdir = tmp_path / "2024"
        _place(fixture=FIXTURE_A, destination=subdir / "DSCF0001.JPG")
        _place(fixture=FIXTURE_B, destination=subdir / "DSCF0002.jpg")
        sync_folder(folder_id=folder.pk)
        original_ids = set(models.Image.objects.values_list("pk", flat=True))
        for image in models.Image.objects.all():
            image.set_rating(2)

        renamed = tmp_path / "2024-spain"
        subdir.rename(renamed)
        sync_folder(folder_id=folder.pk)

        assert set(models.Image.objects.values_list("pk", flat=True)) == original_ids
        assert _catalogued() == {
            str(renamed / "DSCF0001.JPG"),
            str(renamed / "DSCF0002.jpg"),
        }
        assert all(image.rating == 2 for image in models.Image.objects.all())

    def test_12_a_subfolder_moved_in_from_outside_is_imported(self, tmp_path):
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        folder = LibraryFolderFactory(path=str(library_dir))
        sync_folder(folder_id=folder.pk)

        incoming = tmp_path / "incoming"
        _place(fixture=FIXTURE_A, destination=incoming / "DSCF0001.JPG")
        incoming.rename(library_dir / "incoming")
        sync_folder(folder_id=folder.pk)

        assert _catalogued() == {str(library_dir / "incoming" / "DSCF0001.JPG")}


class TestFolderLevelScenarios:
    def test_13_removing_a_folder_only_keeps_its_images(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        removed = remove_library_folder(folder_id=folder.pk, delete_images=False)

        assert removed == 0
        assert models.Image.objects.count() == 1

    def test_14_removing_a_folder_with_its_images_empties_the_gallery(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _place(fixture=FIXTURE_A, destination=tmp_path / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)

        removed = remove_library_folder(folder_id=folder.pk, delete_images=True)

        assert removed == 1
        assert models.Image.objects.count() == 0
        assert photo.exists()

    def test_15_a_folder_moved_on_disk_relocates_its_images(self, tmp_path):
        old_dir = tmp_path / "photos"
        old_dir.mkdir()
        folder = LibraryFolderFactory(path=str(old_dir))
        _place(fixture=FIXTURE_A, destination=old_dir / "2024" / "DSCF0001.JPG")
        sync_folder(folder_id=folder.pk)
        image = models.Image.objects.get()
        image.set_rating(5)

        new_dir = tmp_path / "pictures"
        old_dir.rename(new_dir)
        update_library_folder_path(folder_id=folder.pk, path=str(new_dir))
        sync_folder(folder_id=folder.pk)

        image.refresh_from_db()
        assert models.Image.objects.count() == 1
        assert image.filepath == str(new_dir / "2024" / "DSCF0001.JPG")
        assert image.rating == 5

    def test_16_a_folder_missing_from_disk_removes_nothing(self, tmp_path):
        library_dir = tmp_path / "external-drive"
        library_dir.mkdir()
        folder = LibraryFolderFactory(path=str(library_dir))
        _place(fixture=FIXTURE_A, destination=library_dir / "DSCF0001.JPG")
        _place(fixture=FIXTURE_B, destination=library_dir / "DSCF0002.jpg")
        sync_folder(folder_id=folder.pk)
        assert models.Image.objects.count() == 2

        shutil.rmtree(library_dir)
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 2
        run = models.SyncRun.objects.order_by("-id").first()
        assert run.state == models.SyncRun.STATE_FAILED
        assert run.failure_reason == models.SyncRun.FAILED_FOLDER_MISSING
        assert run.removed == 0

    def test_17_removing_a_nested_folder_keeps_images_the_outer_one_covers(self, tmp_path):
        outer = LibraryFolderFactory(path=str(tmp_path))
        inner_dir = tmp_path / "2024"
        _place(fixture=FIXTURE_A, destination=inner_dir / "DSCF0001.JPG")
        inner = LibraryFolderFactory(path=str(inner_dir))
        sync_folder(folder_id=outer.pk)
        assert models.Image.objects.count() == 1

        removed = remove_library_folder(folder_id=inner.pk, delete_images=True)

        assert removed == 0
        assert models.Image.objects.count() == 1

    def test_18_an_image_outside_every_tracked_folder_is_never_removed(self, tmp_path):
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        folder = LibraryFolderFactory(path=str(library_dir))
        # Imported by hand from a folder that was never registered.
        outside = _place(fixture=FIXTURE_A, destination=tmp_path / "elsewhere" / "DSCF0001.JPG")
        process_image(image_path=str(outside))
        outside.unlink()

        sync_folder(folder_id=folder.pk)

        assert _catalogued() == {str(outside)}

    def test_19_a_symlinked_subfolder_is_never_pruned(self, tmp_path):
        library_dir = tmp_path / "library"
        library_dir.mkdir()
        real_dir = tmp_path / "real"
        photo = _place(fixture=FIXTURE_A, destination=real_dir / "DSCF0001.JPG")
        folder = LibraryFolderFactory(path=str(library_dir))
        (library_dir / "linked").symlink_to(real_dir)

        # os.walk does not follow the symlink, so the sync never imports through
        # it. Import the path by hand to put the record where a prune would see it.
        linked_path = str(library_dir / "linked" / "DSCF0001.JPG")
        process_image(image_path=linked_path)

        sync_folder(folder_id=folder.pk)

        assert linked_path in _catalogued()
        assert photo.exists()


class TestFolderPathChangeScenarios:
    """
    Changing a folder's path moves the boundary rather than the files. Narrowing
    it leaves images outside the new path belonging to nothing; repointing it at
    a folder that moved leaves them belonging to the same folder at a new path.
    The two need opposite treatment.
    """

    def test_20_narrowing_a_folder_removes_what_falls_outside_it(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        _place(fixture=FIXTURE_A, destination=tmp_path / "2023" / "a.jpg")
        _place(fixture=FIXTURE_B, destination=tmp_path / "2023" / "b.jpg")
        kept = _place(fixture=FIXTURE_C, destination=tmp_path / "2024" / "c.jpg")
        sync_folder(folder_id=folder.pk)
        assert models.Image.objects.count() == 3

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path / "2024"))
        sync_folder(folder_id=folder.pk)

        assert _catalogued() == {str(kept)}

    def test_20_narrowing_leaves_the_photo_files_alone(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        outside = _place(fixture=FIXTURE_A, destination=tmp_path / "2023" / "a.jpg")
        _place(fixture=FIXTURE_C, destination=tmp_path / "2024" / "c.jpg")
        sync_folder(folder_id=folder.pk)

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path / "2024"))
        sync_folder(folder_id=folder.pk)

        assert outside.exists()

    def test_20_re_widening_the_folder_brings_them_back(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        _place(fixture=FIXTURE_A, destination=tmp_path / "2023" / "a.jpg")
        _place(fixture=FIXTURE_C, destination=tmp_path / "2024" / "c.jpg")
        sync_folder(folder_id=folder.pk)

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path / "2024"))
        sync_folder(folder_id=folder.pk)
        assert models.Image.objects.count() == 1

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path))
        sync_folder(folder_id=folder.pk)

        assert models.Image.objects.count() == 2

    def test_21_repointing_a_moved_folder_still_relocates_rather_than_removes(self, tmp_path):
        # The case the obvious fix breaks: removing at path-change time would
        # delete these records before the sync could recognise and repoint them.
        old_dir = tmp_path / "photos"
        old_dir.mkdir()
        folder = LibraryFolderFactory(path=str(old_dir))
        _place(fixture=FIXTURE_A, destination=old_dir / "2024" / "a.jpg")
        _place(fixture=FIXTURE_B, destination=old_dir / "2024" / "b.jpg")
        sync_folder(folder_id=folder.pk)
        original_ids = set(models.Image.objects.values_list("pk", flat=True))
        for image in models.Image.objects.all():
            image.set_rating(4)

        new_dir = tmp_path / "pictures"
        old_dir.rename(new_dir)
        update_library_folder_path(folder_id=folder.pk, path=str(new_dir))
        sync_folder(folder_id=folder.pk)

        assert set(models.Image.objects.values_list("pk", flat=True)) == original_ids
        assert all(image.rating == 4 for image in models.Image.objects.all())
        assert _catalogued() == {
            str(new_dir / "2024" / "a.jpg"),
            str(new_dir / "2024" / "b.jpg"),
        }

    def test_22_narrowing_keeps_images_a_second_registered_folder_covers(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        shared = _place(fixture=FIXTURE_A, destination=tmp_path / "2023" / "a.jpg")
        kept = _place(fixture=FIXTURE_C, destination=tmp_path / "2024" / "c.jpg")
        LibraryFolderFactory(path=str(tmp_path / "2023"))
        sync_folder(folder_id=folder.pk)

        update_library_folder_path(folder_id=folder.pk, path=str(tmp_path / "2024"))
        sync_folder(folder_id=folder.pk)

        assert _catalogued() == {str(shared), str(kept)}
