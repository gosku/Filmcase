# Web Interface

## Gallery

The main gallery shows all imported images as a scrollable grid. As you scroll down, more
images load automatically.

### Filtering

A sidebar lets you narrow the gallery by recipe settings: film simulation, dynamic range,
grain, white balance, and other creative fields. Filters update the grid without reloading
the page.

Filtering is **faceted**: selecting a value in one field instantly updates the available
choices in every other field to only show combinations that exist in your library. You can
select **multiple values within the same field** (e.g. Provia and Velvia at once) — images
matching any of those values are shown. Values that have been selected but are no longer
reachable given the other active filters are shown greyed-out; unchecking a conflicting
filter brings them back.

You can also **filter by recipe** using the searchable multi-select at the top of the
sidebar. Choosing one or more recipes narrows all other filter options to that recipe's
images, and conversely, active field filters update the recipe list to reflect only recipes
that have matching images.

A **Clear all filters** link at the top of the sidebar resets everything in one click.

You can also enable **Rating first** to sort the grid by rating (highest first), so your
best-rated images always appear at the top.

---

## Image Detail

Clicking an image opens a full-resolution detail view with all of its EXIF information,
including the complete recipe the camera had active at the time of shooting.

From the detail view you can:

- **Browse** to the previous or next image within your current filter, without going back to
  the gallery.
- **Rate the image** using the star widget (0–`IMAGE_MAX_RATING`). Click a star to set that
  rating; click the clear button (✕) to reset it to 0.
- **Name the recipe** — if the image's recipe has no name yet, a prompt appears inline.
  Names are limited to 25 ASCII characters, matching the camera's own slot naming rules. See
  [recipe_naming.md](recipe_naming.md) for more detail.
- **Send the recipe to your camera** — once a recipe has a name, you can write it to one of
  your camera's custom slots (C1–C7) over USB. The interface shows you what is already saved
  in each slot so you can choose where to write.
