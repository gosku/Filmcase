"""
Queries backing the gallery date timeline: a monthly distribution for the rail,
and keyset (seek) pagination so the gallery can jump to a date and scroll both
ways from there.

Keyset pagination orders by a total key and pages by comparing against a
cursor, rather than counting rows with OFFSET. Two orderings are supported and
mirror the gallery's own orderings exactly:

- chronological: ``taken_at DESC NULLS LAST, id ASC``
- rating-first:  ``rating DESC, taken_at DESC NULLS LAST, id ASC``

``taken_at`` is nullable, so the seek predicate is built with explicit null
handling (nulls sort last) rather than relying on a backend's default, which
differs between SQLite and PostgreSQL.
"""
import base64
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, tzinfo
from enum import Enum

import attrs
from django.db import models as db_models
from django.db.models.functions import TruncMonth

from src.data import models
from src.domain.images import filter_queries


class Direction(Enum):
    OLDER = "older"
    NEWER = "newer"


@attrs.frozen
class InvalidCursor(Exception):
    """Raised when a cursor string cannot be decoded."""

    raw: str


@attrs.frozen
class Cursor:
    taken_at: datetime | None
    image_id: int
    rating: int


@attrs.frozen
class TimelineMonth:
    year: int
    month: int
    count: int


@attrs.frozen
class TimelineDistribution:
    months: tuple[TimelineMonth, ...]
    total: int
    undated_count: int


@attrs.frozen
class ImagePage:
    images: tuple[models.Image, ...]
    newer_cursor: str | None
    older_cursor: str | None
    has_newer: bool
    has_older: bool


def encode_cursor(*, image: models.Image) -> str:
    """Encode an image's ordering keys into an opaque, URL-safe cursor string."""
    payload = {
        "t": image.taken_at.isoformat() if image.taken_at is not None else None,
        "id": image.pk,
        "r": image.rating,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(*, raw: str) -> Cursor:
    """
    Decode a cursor string produced by :func:`encode_cursor`.

    :raises InvalidCursor: if the string is not a cursor this module produced.
    """
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        taken_at_raw = payload["t"]
        return Cursor(
            taken_at=datetime.fromisoformat(taken_at_raw) if taken_at_raw is not None else None,
            image_id=int(payload["id"]),
            rating=int(payload["r"]),
        )
    except (ValueError, KeyError, TypeError):
        raise InvalidCursor(raw=raw)


def get_timeline_distribution(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    tz: tzinfo,
) -> TimelineDistribution:
    """
    Count the filtered images per month for the timeline rail.

    Computed over the date-ordered region the rail navigates: the whole filtered
    set in chronological mode, or the unrated (rating 0) tail in rating-first
    mode. Undated images are reported as a separate count, not as a month.
    Months are truncated in *tz* so photos near midnight fall in the right month.
    """
    region = _date_ordered_region(active_filters=active_filters, rating_first=rating_first)
    undated_count = region.filter(taken_at__isnull=True).count()
    month_rows = (
        region.filter(taken_at__isnull=False)
        .order_by()  # clear the base ordering so it does not enter the GROUP BY
        .annotate(month=TruncMonth("taken_at", tzinfo=tz))
        .values("month")
        .annotate(count=db_models.Count("id"))
        .order_by("-month")
    )
    months = tuple(
        TimelineMonth(year=row["month"].year, month=row["month"].month, count=row["count"])
        for row in month_rows
    )
    return TimelineDistribution(
        months=months,
        total=sum(month.count for month in months),
        undated_count=undated_count,
    )


def get_images_page(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    cursor: str | None,
    direction: Direction,
    limit: int,
) -> ImagePage:
    """
    Return one keyset page of the filtered gallery.

    *cursor* ``None`` starts at the newest image. *direction* OLDER pages
    downward (older), NEWER pages upward (newer). Rows are always returned in
    natural display order (newest first).

    :raises InvalidCursor: if *cursor* is not decodable.
    """
    base = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    if cursor is not None:
        seek = _seek_q(rating_first=rating_first, cursor=decode_cursor(raw=cursor), direction=direction)
        base = base.filter(seek)
    ordered = _ordered(base, rating_first=rating_first, natural=direction is Direction.OLDER)
    rows = list(ordered[: limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    if direction is Direction.NEWER:
        rows.reverse()
    return _page_from_rows(
        active_filters=active_filters,
        rating_first=rating_first,
        rows=rows,
        has_more=has_more,
        direction=direction,
        had_cursor=cursor is not None,
    )


def get_images_from_date(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    target: datetime,
    limit: int,
) -> ImagePage:
    """
    Return the landing page for a jump to a date: the newest images at or older
    than *target* within the date-ordered region.

    *target* is the exclusive upper bound (the first moment of the month after
    the one jumped to), so the newest matching image is the newest one in the
    jumped-to month, or the closest earlier month when it is empty. In
    rating-first mode this lands in the unrated tail, after the rated block.
    """
    region = _date_ordered_region(active_filters=active_filters, rating_first=rating_first)
    ordered = _ordered(region.filter(taken_at__lt=target), rating_first=rating_first, natural=True)
    rows = list(ordered[: limit + 1])
    has_older = len(rows) > limit
    rows = rows[:limit]
    return _page_from_rows(
        active_filters=active_filters,
        rating_first=rating_first,
        rows=rows,
        has_more=has_older,
        direction=Direction.OLDER,
        had_cursor=True,
    )


def _date_ordered_region(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
) -> db_models.QuerySet[models.Image]:
    """The contiguous date-ordered region the timeline navigates."""
    region = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    if rating_first:
        # Rated photos are a leading block; only the unrated tail is date-ordered.
        region = region.filter(rating=0)
    return region


def _ordered(
    qs: db_models.QuerySet[models.Image],
    *,
    rating_first: bool,
    natural: bool,
) -> db_models.QuerySet[models.Image]:
    """Apply the gallery ordering (natural) or its reverse (for a NEWER page)."""
    keys: list[str | db_models.OrderBy]
    if natural:
        keys = [db_models.F("taken_at").desc(nulls_last=True), "id"]
        if rating_first:
            keys.insert(0, "-rating")
    else:
        keys = [db_models.F("taken_at").asc(nulls_first=True), "-id"]
        if rating_first:
            keys.insert(0, "rating")
    return qs.order_by(*keys)


def _page_from_rows(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    rows: list[models.Image],
    has_more: bool,
    direction: Direction,
    had_cursor: bool,
) -> ImagePage:
    if not rows:
        return ImagePage(images=(), newer_cursor=None, older_cursor=None, has_newer=False, has_older=False)
    newer_cursor = encode_cursor(image=rows[0])
    older_cursor = encode_cursor(image=rows[-1])
    if direction is Direction.OLDER:
        # Fetched rows older than the cursor: more-older is has_more; newer
        # exists whenever we sought from a cursor (a jump, or a scroll-down).
        has_older = has_more
        has_newer = _exists_newer(
            active_filters=active_filters, rating_first=rating_first, image=rows[0]
        ) if had_cursor else False
    else:
        has_newer = has_more
        has_older = True
    return ImagePage(
        images=tuple(rows),
        newer_cursor=newer_cursor,
        older_cursor=older_cursor,
        has_newer=has_newer,
        has_older=has_older,
    )


def _exists_newer(
    *,
    active_filters: Mapping[str, Sequence[str]],
    rating_first: bool,
    image: models.Image,
) -> bool:
    base = filter_queries.get_filtered_images(active_filters=active_filters, rating_first=rating_first)
    seek = _seek_q(rating_first=rating_first, cursor=_cursor_from_image(image), direction=Direction.NEWER)
    return base.filter(seek).exists()


def _cursor_from_image(image: models.Image) -> Cursor:
    return Cursor(taken_at=image.taken_at, image_id=image.pk, rating=image.rating)


def _seek_q(*, rating_first: bool, cursor: Cursor, direction: Direction) -> db_models.Q:
    """
    Build the keyset predicate selecting rows strictly after (OLDER) or before
    (NEWER) *cursor* in the active ordering, expanded lexicographically over the
    ordering keys with explicit nulls-last handling for ``taken_at``.
    """
    later = direction is Direction.OLDER
    combined: db_models.Q | None = None
    prefix = db_models.Q()
    for field, descending, nullable, value in _ordering_keys(rating_first=rating_first, cursor=cursor):
        step = _step_q(field=field, descending=descending, nullable=nullable, value=value, later=later)
        if step is not None:
            term = prefix & step
            combined = term if combined is None else combined | term
        prefix = prefix & _eq_q(field=field, value=value)
    if combined is None:  # unreachable: the non-null id key always yields a step
        return db_models.Q(pk__in=[])
    return combined


def _ordering_keys(
    *,
    rating_first: bool,
    cursor: Cursor,
) -> list[tuple[str, bool, bool, object]]:
    """(field, descending, nullable, cursor value) for each ordering key."""
    keys: list[tuple[str, bool, bool, object]] = []
    if rating_first:
        keys.append(("rating", True, False, cursor.rating))
    keys.append(("taken_at", True, True, cursor.taken_at))
    keys.append(("id", False, False, cursor.image_id))
    return keys


def _eq_q(*, field: str, value: object) -> db_models.Q:
    if value is None:
        return db_models.Q(**{f"{field}__isnull": True})
    return db_models.Q(**{field: value})


def _step_q(
    *,
    field: str,
    descending: bool,
    nullable: bool,
    value: object,
    later: bool,
) -> db_models.Q | None:
    """
    Predicate for rows sorting strictly later (``later=True``) or earlier at a
    single key. Returns ``None`` when no row can sort later at this key (a null
    value under DESC-nulls-last, where ties fall through to the next key).
    """
    if not descending:  # ascending, non-null (id)
        return db_models.Q(**{f"{field}__{'gt' if later else 'lt'}": value})
    if not nullable:  # descending, non-null (rating)
        return db_models.Q(**{f"{field}__{'lt' if later else 'gt'}": value})
    # descending, nullable (taken_at), nulls last
    if value is None:
        if later:
            return None
        return db_models.Q(**{f"{field}__isnull": False})
    if later:
        return db_models.Q(**{f"{field}__lt": value}) | db_models.Q(**{f"{field}__isnull": True})
    return db_models.Q(**{f"{field}__gt": value})
