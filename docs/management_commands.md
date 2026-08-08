# Management Commands

Management commands are run from the terminal and handle tasks that don't belong in the
web interface (yet)— bulk imports, maintenance, and camera inspection.

## Running commands

The project uses a virtualenv located at `.venv/`. To run any management command, prefix
it with `.venv/bin/python` instead of `python`:

```bash
.venv/bin/python manage.py <command> [args]
```

Alternatively, activate the virtualenv for your shell session first:

```bash
source .venv/bin/activate
python manage.py <command> [args]
```

---

## Syncing the library

```
python manage.py sync_library
```

Scans all folders registered in the Library, finds JPEG files not yet in the catalog, imports
them, and takes out of the gallery any entry whose file has disappeared. This command is run
automatically by `make start` before the web server starts, so in normal use you do not need to
call it directly.

Removing an entry never deletes the photo file: it only removes Filmcase's record of it. A
photo you renamed or moved is recognised by its contents and keeps its rating and favourite
mark rather than being removed and re-imported.

If a registered folder is no longer present on disk, a warning is printed, **nothing is removed
from the gallery**, and the remaining folders are still scanned.

Three flags control removal (they are mutually exclusive):

| Flag | Effect |
|---|---|
| `--dry-run-prune` | List which entries would be removed, and remove none |
| `--force-prune` | Remove even when the mass-removal safety guard would stop it |
| `--no-prune` | Import only; never remove anything |

The safety guard stops a pass that would remove more than half of a folder's images and more
than twenty of them, since that usually means a drive is not mounted rather than that the
photos were deleted. See `docs/library_sync.md` for the full picture.

Behaviour depends on your install mode:

- **Lite install** (`USE_ASYNC_TASKS=False`): new images are processed in the foreground
  before the command exits.
- **Full install** (`USE_ASYNC_TASKS=True`): one Celery task is enqueued per new image and
  processed in parallel by the worker. The command exits as soon as all tasks are queued. If
  no Celery worker is reachable, the sync is skipped with a warning.

See [Library Sync](library_sync.md) for a detailed explanation of the sync algorithm.

---

## Importing images

```
python manage.py process_images <folder>
```

Scans a folder for JPEG images taken with a Fujifilm camera and imports them into the
application, extracting recipe and EXIF data from each file.

Behaviour depends on your install mode:

- **Lite install** (`USE_ASYNC_TASKS=False`): images are processed one at a time in the
  foreground. The terminal blocks until all images are done.
- **Full install** (`USE_ASYNC_TASKS=True`): one Celery task is enqueued per image and
  processed in parallel by the worker (start it first with `make worker`).

Files that cannot produce a recipe are skipped, never aborting the run. That covers
images carrying no Fujifilm metadata, and images whose EXIF fails recipe validation,
such as a colour simulation whose Color the camera set rather than the user. In lite
mode the command reports how many were skipped; add `--verbosity 2` to list their
paths. In full install mode each skip is recorded as an `image.import.skipped` event
in the worker log, carrying the reason and the offending recipe field.

---

## Rating images in bulk

```
python manage.py rate_images <folder> --rating=<value>
```

Applies a rating to every image in a folder. Useful when you have already curated a
selection of images outside the app (e.g. a folder of exports from your camera, editing
software, Google Photos...) and want that rating reflected in the gallery without clicking
through each image individually.

`--rating` accepts any integer from 0 to `IMAGE_MAX_RATING` (default 5). Use `--rating=0`
to clear ratings in bulk.

Images are matched to your catalogue by reading their EXIF metadata — not by filename,
since export tools often rename files. The command tries a series of increasingly broad
strategies (date + filename, date + shutter counter, date + film simulation, etc.) until it
finds a unique match. If no match is found, the image is imported as a new entry and rated.
See [favorite_image_matching.md](favorite_image_matching.md) for the full matching logic.

---

## Pre-generating thumbnails

```
python manage.py generate_thumbnails
```

Generates thumbnail cache for all images in the database. The web interface creates
thumbnails on demand, but running this command upfront means the gallery loads at full speed
from the first visit, with no on-the-fly resizing.

---

## Inspecting camera slots

```
python manage.py camera_info
python manage.py camera_info --slots
```

Connects to a Fujifilm camera over USB and reports its model, battery level, and firmware
version. Adding `--slots` also reads the contents of each custom slot (C1–C7), showing
what name and film simulation is currently saved in each one.

This is read-only — nothing on the camera is changed. Useful for checking the state of your
camera before or after pushing a recipe from the web interface.

---

## Comparing recipes

```
python manage.py compare_recipes <id> [<id> ...]
```

Prints a side-by-side comparison of two or more recipes, showing every setting and how many
photos were shot with each one. Also shows a monthly breakdown of usage, which is useful for
understanding how a recipe evolved in your workflow over time.

Recipe IDs can be found in the URL when viewing an image in the web interface.
