from datetime import datetime, timezone

import pytest

from src.data import models
from src.domain.images import timeline_queries


class TestEncodeDecodeCursor:
    def test_round_trips_a_dated_image(self) -> None:
        image = models.Image(id=42, taken_at=datetime(2020, 12, 25, 9, 30, tzinfo=timezone.utc), rating=3)
        cursor = timeline_queries.decode_cursor(raw=timeline_queries.encode_cursor(image=image))
        assert cursor == timeline_queries.Cursor(
            taken_at=datetime(2020, 12, 25, 9, 30, tzinfo=timezone.utc),
            image_id=42,
            rating=3,
        )

    def test_round_trips_an_undated_image(self) -> None:
        image = models.Image(id=7, taken_at=None, rating=0)
        cursor = timeline_queries.decode_cursor(raw=timeline_queries.encode_cursor(image=image))
        assert cursor == timeline_queries.Cursor(taken_at=None, image_id=7, rating=0)

    def test_cursor_is_url_safe(self) -> None:
        image = models.Image(id=1, taken_at=datetime(2026, 1, 1, tzinfo=timezone.utc), rating=5)
        raw = timeline_queries.encode_cursor(image=image)
        assert raw == raw.strip()
        assert "/" not in raw and "+" not in raw

    def test_raises_on_a_garbage_cursor(self) -> None:
        with pytest.raises(timeline_queries.InvalidCursor):
            timeline_queries.decode_cursor(raw="not-a-real-cursor!!")

    def test_raises_on_a_cursor_missing_keys(self) -> None:
        import base64
        import json

        raw = base64.urlsafe_b64encode(json.dumps({"t": None}).encode()).decode()
        with pytest.raises(timeline_queries.InvalidCursor):
            timeline_queries.decode_cursor(raw=raw)
