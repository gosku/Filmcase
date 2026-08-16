import shutil
from pathlib import Path

import pytest

from src.data import models
from src.domain.images import events
from src.domain.images.operations import process_image
from tests.factories import ImageFactory

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "fixtures" / "images"
FIXTURE_IMAGE = str(FIXTURES_DIR / "XS107114.JPG")


def _copy_fixture(*, destination: Path) -> str:
    """Copy XS107114.JPG to *destination*, creating parent folders, and return its path."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_IMAGE, destination)
    return str(destination)


@pytest.mark.django_db
class TestProcessImageRelocatesMovedFiles:
    def test_a_moved_file_keeps_its_record(self, tmp_path):
        old_path = _copy_fixture(destination=tmp_path / "inbox" / "XS107114.JPG")
        original = process_image(image_path=old_path)

        new_path = str(tmp_path / "2025" / "XS107114.JPG")
        Path(new_path).parent.mkdir()
        shutil.move(old_path, new_path)

        moved = process_image(image_path=new_path)

        assert moved.pk == original.pk
        assert models.Image.objects.count() == 1
        assert moved.filepath == new_path

    def test_a_renamed_file_keeps_its_record_and_gains_the_new_filename(self, tmp_path):
        old_path = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        original = process_image(image_path=old_path)

        new_path = str(tmp_path / "spain-2025.JPG")
        shutil.move(old_path, new_path)

        renamed = process_image(image_path=new_path)

        assert renamed.pk == original.pk
        assert renamed.filepath == new_path
        assert renamed.filename == "spain-2025.JPG"

    def test_a_moved_file_keeps_its_rating_and_favourite(self, tmp_path):
        old_path = _copy_fixture(destination=tmp_path / "inbox" / "XS107114.JPG")
        original = process_image(image_path=old_path)
        original.set_rating(5)
        original.set_as_favorite()
        original.set_as_in_album()

        new_path = str(tmp_path / "keepers" / "XS107114.JPG")
        Path(new_path).parent.mkdir()
        shutil.move(old_path, new_path)

        moved = process_image(image_path=new_path)

        assert moved.pk == original.pk
        assert moved.rating == 5
        assert moved.is_favorite is True
        assert moved.in_album is True

    def test_a_copy_alongside_the_original_leaves_the_record_where_it_is(self, tmp_path):
        original_path = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        original = process_image(image_path=original_path)

        copy_path = _copy_fixture(destination=tmp_path / "backup" / "XS107114.JPG")
        result = process_image(image_path=copy_path)

        assert result.pk == original.pk
        assert models.Image.objects.count() == 1
        assert result.filepath == original_path

    def test_publishes_image_file_relocated_for_a_move(self, tmp_path, captured_logs):
        old_path = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        process_image(image_path=old_path)

        new_path = str(tmp_path / "moved.JPG")
        shutil.move(old_path, new_path)
        process_image(image_path=new_path)

        matching = [e for e in captured_logs if e.get("event_type") == events.IMAGE_FILE_RELOCATED]
        assert len(matching) == 1
        assert matching[0]["old_filepath"] == old_path
        assert matching[0]["new_filepath"] == new_path

    def test_does_not_relocate_onto_a_path_another_record_already_holds(self, tmp_path):
        old_path = _copy_fixture(destination=tmp_path / "XS107114.JPG")
        original = process_image(image_path=old_path)

        # A legacy record already sits at the destination. Relocating onto it
        # would violate the unique filepath constraint.
        new_path = str(tmp_path / "occupied.JPG")
        squatter = ImageFactory(filepath=new_path, content_hash="")
        shutil.move(old_path, new_path)

        result = process_image(image_path=new_path)

        assert result.pk == original.pk
        assert result.filepath == old_path
        squatter.refresh_from_db()
        assert squatter.filepath == new_path
