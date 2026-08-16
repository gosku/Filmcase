import datetime
import os

import pytest

from src.data import models
from src.domain.library import events
from src.domain.library.operations import (
    forget_ignored_image,
    forget_ignored_images,
    forget_ignored_path,
    record_ignored_image,
)
from src.domain.library.queries import IgnoredImageNotFound
from tests.factories import IgnoredImageFactory, LibraryFolderFactory


def _photo(*, folder_path, name="other_brand.jpg", content=b"\xff\xd8abc"):
    path = folder_path / name
    path.write_bytes(content)
    return path


@pytest.mark.django_db
class TestRecordIgnoredImage:
    def test_records_the_file_with_its_current_fingerprint(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path)

        ignored = record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
            detail="",
        )

        assert ignored.filepath == str(photo)
        assert ignored.file_size == photo.stat().st_size
        assert ignored.file_modified_at == datetime.datetime.fromtimestamp(
            photo.stat().st_mtime, tz=datetime.timezone.utc
        )

    def test_keeps_the_file_on_disk(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path)

        record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_ERROR,
            detail="boom",
        )

        assert photo.exists()

    def test_stores_the_detail_for_an_error(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path)

        ignored = record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_ERROR,
            detail="OSError: disk went away",
        )

        assert ignored.detail == "OSError: disk went away"

    def test_re_recording_a_changed_file_updates_its_fingerprint(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path)
        first = record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
            detail="",
        )
        original_size = first.file_size

        photo.write_bytes(b"\xff\xd8" + b"much longer content")
        second = record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_ERROR,
            detail="failed again",
        )

        assert second.pk == first.pk
        assert models.IgnoredImage.objects.count() == 1
        assert second.file_size != original_size
        assert second.reason == models.IgnoredImage.REASON_ERROR
        assert second.detail == "failed again"

    def test_publishes_image_ignored(self, tmp_path, captured_logs):
        folder = LibraryFolderFactory(path=str(tmp_path))
        photo = _photo(folder_path=tmp_path)

        record_ignored_image(
            folder=folder,
            filepath=str(photo),
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
            detail="",
        )

        matching = [e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORED]
        assert len(matching) == 1
        assert matching[0]["filepath"] == str(photo)
        assert matching[0]["reason"] == models.IgnoredImage.REASON_NO_FILM_SIMULATION

    def test_raises_when_the_file_cannot_be_stated(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))

        with pytest.raises(OSError):
            record_ignored_image(
                folder=folder,
                filepath=str(tmp_path / "gone.jpg"),
                reason=models.IgnoredImage.REASON_ERROR,
                detail="",
            )


@pytest.mark.django_db
class TestForgetIgnoredImage:
    def test_removes_the_record_and_returns_its_path(self):
        ignored = IgnoredImageFactory(filepath="/photos/other.jpg")

        assert forget_ignored_image(ignored_id=ignored.pk) == "/photos/other.jpg"
        assert not models.IgnoredImage.objects.filter(pk=ignored.pk).exists()

    def test_keeps_the_file_on_disk(self, tmp_path):
        photo = _photo(folder_path=tmp_path)
        ignored = IgnoredImageFactory(filepath=str(photo))

        forget_ignored_image(ignored_id=ignored.pk)

        assert photo.exists()

    def test_publishes_ignore_removed(self, captured_logs):
        ignored = IgnoredImageFactory()

        forget_ignored_image(ignored_id=ignored.pk)

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORE_REMOVED
        ]
        assert len(matching) == 1

    def test_raises_ignored_image_not_found_for_unknown_id(self):
        with pytest.raises(IgnoredImageNotFound) as exc_info:
            forget_ignored_image(ignored_id=9999)

        assert exc_info.value.ignored_id == 9999


@pytest.mark.django_db
class TestForgetIgnoredPath:
    def test_forgets_a_path_that_was_ignored(self):
        ignored = IgnoredImageFactory(filepath="/photos/other.jpg")

        assert forget_ignored_path(filepath="/photos/other.jpg") is True
        assert not models.IgnoredImage.objects.filter(pk=ignored.pk).exists()

    def test_reports_false_for_a_path_that_was_not_ignored(self):
        assert forget_ignored_path(filepath="/photos/never-seen.jpg") is False

    def test_leaves_other_records_alone(self):
        kept = IgnoredImageFactory(filepath="/photos/a.jpg")
        IgnoredImageFactory(filepath="/photos/b.jpg")

        forget_ignored_path(filepath="/photos/b.jpg")

        assert list(models.IgnoredImage.objects.values_list("pk", flat=True)) == [kept.pk]

    def test_publishes_ignore_removed(self, captured_logs):
        IgnoredImageFactory(filepath="/photos/other.jpg")

        forget_ignored_path(filepath="/photos/other.jpg")

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORE_REMOVED
        ]
        assert len(matching) == 1

    def test_publishes_nothing_when_there_was_no_record(self, captured_logs):
        forget_ignored_path(filepath="/photos/never-seen.jpg")

        assert [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORE_REMOVED
        ] == []


@pytest.mark.django_db
class TestForgetIgnoredImages:
    def test_forgets_every_record_in_the_folder(self):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=folder, filepath="/a/1.jpg")
        IgnoredImageFactory(folder=folder, filepath="/a/2.jpg")

        assert forget_ignored_images(folder_id=folder.pk) == 2
        assert models.IgnoredImage.objects.count() == 0

    def test_forgets_only_the_requested_reason(self):
        folder = LibraryFolderFactory()
        kept = IgnoredImageFactory(
            folder=folder,
            filepath="/a/1.jpg",
            reason=models.IgnoredImage.REASON_NO_FILM_SIMULATION,
        )
        IgnoredImageFactory(
            folder=folder,
            filepath="/a/2.jpg",
            reason=models.IgnoredImage.REASON_ERROR,
        )

        count = forget_ignored_images(folder_id=folder.pk, reason=models.IgnoredImage.REASON_ERROR)

        assert count == 1
        assert list(models.IgnoredImage.objects.values_list("pk", flat=True)) == [kept.pk]

    def test_leaves_another_folders_records_alone(self):
        folder = LibraryFolderFactory()
        other = IgnoredImageFactory(folder=LibraryFolderFactory())

        forget_ignored_images(folder_id=folder.pk)

        assert models.IgnoredImage.objects.filter(pk=other.pk).exists()

    def test_reports_zero_and_publishes_nothing_when_there_is_nothing_to_forget(self, captured_logs):
        folder = LibraryFolderFactory()

        assert forget_ignored_images(folder_id=folder.pk) == 0
        assert [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORES_CLEARED
        ] == []

    def test_publishes_ignores_cleared_with_the_count(self, captured_logs):
        folder = LibraryFolderFactory()
        IgnoredImageFactory(folder=folder, filepath="/a/1.jpg")
        IgnoredImageFactory(folder=folder, filepath="/a/2.jpg")

        forget_ignored_images(folder_id=folder.pk)

        matching = [
            e for e in captured_logs if e.get("event_type") == events.LIBRARY_IMAGE_IGNORES_CLEARED
        ]
        assert len(matching) == 1
        assert matching[0]["count"] == 2


@pytest.mark.django_db
class TestRemovingAFolderForgetsItsIgnoredImages:
    def test_records_go_with_the_folder(self, tmp_path):
        folder = LibraryFolderFactory(path=str(tmp_path))
        IgnoredImageFactory(folder=folder, filepath=str(tmp_path / "other.jpg"))

        folder.delete()

        assert models.IgnoredImage.objects.count() == 0
