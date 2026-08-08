import pytest

from src.domain.images import events
from src.domain.images.operations import relocate_image
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestRelocateImage:
    def test_repoints_a_record_whose_file_has_moved(self, tmp_path):
        new_file = tmp_path / "2024" / "DSCF0002.JPG"
        new_file.parent.mkdir()
        new_file.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"), filename="DSCF0001.JPG")

        assert relocate_image(image=image, new_path=str(new_file)) is True

        image.refresh_from_db()
        assert image.filepath == str(new_file)
        assert image.filename == "DSCF0002.JPG"

    def test_keeps_user_data_when_the_record_moves(self, tmp_path):
        new_file = tmp_path / "DSCF0002.JPG"
        new_file.write_bytes(b"\xff\xd8")
        image = ImageFactory(
            filepath=str(tmp_path / "DSCF0001.JPG"),
            rating=4,
            is_favorite=True,
            in_album=True,
        )
        original_pk = image.pk

        relocate_image(image=image, new_path=str(new_file))

        image.refresh_from_db()
        assert image.pk == original_pk
        assert image.rating == 4
        assert image.is_favorite is True
        assert image.in_album is True

    def test_leaves_the_record_alone_when_the_old_file_still_exists(self, tmp_path):
        original = tmp_path / "DSCF0001.JPG"
        original.write_bytes(b"\xff\xd8")
        copy = tmp_path / "DSCF0001_copy.JPG"
        copy.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=str(original))

        assert relocate_image(image=image, new_path=str(copy)) is False

        image.refresh_from_db()
        assert image.filepath == str(original)

    def test_leaves_the_record_alone_when_the_path_is_unchanged(self, tmp_path):
        path = tmp_path / "DSCF0001.JPG"
        image = ImageFactory(filepath=str(path))

        assert relocate_image(image=image, new_path=str(path)) is False

    def test_leaves_the_record_alone_when_another_record_holds_the_new_path(self, tmp_path):
        new_path = str(tmp_path / "DSCF0002.JPG")
        ImageFactory(filepath=new_path)
        image = ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"))

        assert relocate_image(image=image, new_path=new_path) is False

        image.refresh_from_db()
        assert image.filepath == str(tmp_path / "DSCF0001.JPG")

    def test_never_touches_either_file_on_disk(self, tmp_path):
        new_file = tmp_path / "DSCF0002.JPG"
        new_file.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=str(tmp_path / "DSCF0001.JPG"))

        relocate_image(image=image, new_path=str(new_file))

        assert new_file.read_bytes() == b"\xff\xd8"

    def test_publishes_image_file_relocated(self, tmp_path, captured_logs):
        old_path = str(tmp_path / "DSCF0001.JPG")
        new_file = tmp_path / "DSCF0002.JPG"
        new_file.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=old_path)

        relocate_image(image=image, new_path=str(new_file))

        matching = [e for e in captured_logs if e.get("event_type") == events.IMAGE_FILE_RELOCATED]
        assert len(matching) == 1
        assert matching[0]["image_id"] == image.pk
        assert matching[0]["old_filepath"] == old_path
        assert matching[0]["new_filepath"] == str(new_file)

    def test_publishes_nothing_when_it_does_not_relocate(self, tmp_path, captured_logs):
        original = tmp_path / "DSCF0001.JPG"
        original.write_bytes(b"\xff\xd8")
        image = ImageFactory(filepath=str(original))

        relocate_image(image=image, new_path=str(tmp_path / "DSCF0002.JPG"))

        assert [e for e in captured_logs if e.get("event_type") == events.IMAGE_FILE_RELOCATED] == []
