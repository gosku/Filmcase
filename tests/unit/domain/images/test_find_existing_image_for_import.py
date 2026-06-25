from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.data import models
from src.domain.images.dataclasses import ImageExifData
from src.domain.images.queries import find_existing_image_for_import

TAKEN_AT = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

# Sentinel: when passed as get_result, Image.objects.get() raises DoesNotExist.
_RAISES_DOES_NOT_EXIST = object()


def _make_objects(*, first_values=(), get_result=_RAISES_DOES_NOT_EXIST):
    """
    Build a mock ``Image.objects`` manager.

    *first_values* are returned by successive ``.filter().order_by().first()``
    calls — the content-hash lookup first, then the EXIF bridge. *get_result*
    is returned by ``.get()``; the default makes it raise ``DoesNotExist``.
    """
    objects = MagicMock()
    objects.filter.return_value.order_by.return_value.first.side_effect = list(first_values)
    if get_result is _RAISES_DOES_NOT_EXIST:
        objects.get.side_effect = models.Image.DoesNotExist
    else:
        objects.get.return_value = get_result
    return objects


def _find(
    *,
    objects,
    content_hash="hash",
    filepath="/p/x.jpg",
    exif=None,
    taken_at=TAKEN_AT,
    filename="x.jpg",
):
    if exif is None:
        exif = ImageExifData(internal_serial_number="SN1", image_count="100")
    with patch("src.domain.images.queries.models.Image.objects", objects):
        return find_existing_image_for_import(
            content_hash=content_hash,
            filepath=filepath,
            exif=exif,
            taken_at=taken_at,
            filename=filename,
        )


class TestFindExistingImageForImport:
    def test_returns_the_hash_match_and_skips_later_lookups(self):
        hash_row = MagicMock()
        objects = _make_objects(first_values=[hash_row])

        result = _find(objects=objects, content_hash="hash")

        assert result is hash_row
        objects.get.assert_not_called()

    def test_skips_the_hash_lookup_when_the_content_hash_is_empty(self):
        filepath_row = MagicMock()
        objects = _make_objects(get_result=filepath_row)

        result = _find(objects=objects, content_hash="")

        assert result is filepath_row
        objects.filter.assert_not_called()

    def test_returns_the_filepath_match_when_the_hash_misses(self):
        filepath_row = MagicMock()
        objects = _make_objects(first_values=[None], get_result=filepath_row)

        result = _find(objects=objects, content_hash="hash")

        assert result is filepath_row

    def test_falls_through_to_the_bridge_when_hash_and_filepath_miss(self):
        bridge_row = MagicMock()
        objects = _make_objects(first_values=[None, bridge_row])

        result = _find(objects=objects, content_hash="hash")

        assert result is bridge_row

    def test_returns_none_when_every_strategy_misses(self):
        objects = _make_objects(first_values=[None, None])

        result = _find(objects=objects, content_hash="hash")

        assert result is None

    def test_bridge_skipped_when_the_serial_number_is_missing(self):
        objects = _make_objects()

        result = _find(
            objects=objects,
            content_hash="",
            exif=ImageExifData(internal_serial_number="", image_count="100"),
        )

        assert result is None
        objects.filter.assert_not_called()

    def test_bridge_skipped_when_the_image_count_is_missing(self):
        objects = _make_objects()

        result = _find(
            objects=objects,
            content_hash="",
            exif=ImageExifData(internal_serial_number="SN1", image_count=""),
        )

        assert result is None
        objects.filter.assert_not_called()

    def test_bridge_skipped_when_the_taken_at_is_missing(self):
        objects = _make_objects()

        result = _find(objects=objects, content_hash="", taken_at=None)

        assert result is None
        objects.filter.assert_not_called()

    def test_bridge_filters_on_the_exif_identity(self):
        bridge_row = MagicMock()
        objects = _make_objects(first_values=[bridge_row])

        result = _find(
            objects=objects,
            content_hash="",
            exif=ImageExifData(internal_serial_number="SN1", image_count="100"),
            taken_at=TAKEN_AT,
            filename="x.jpg",
        )

        assert result is bridge_row
        objects.filter.assert_called_once_with(
            content_hash="",
            fujifilm_exif__internal_serial_number="SN1",
            fujifilm_exif__image_count="100",
            taken_at=TAKEN_AT,
            filename="x.jpg",
        )
