# Management Commands

Management commands are run from the terminal and handle tasks that don't belong in the
web interface (yet)— bulk imports, maintenance, and camera inspection.

---

## Importing images

```
python manage.py process_images <folder>
python manage.py process_images_sync <folder>
```

Both commands scan a folder for JPEG images taken with a Fujifilm camera and import them
into the application, extracting recipe and EXIF data from each file.

`process_images` queues the work in the background (requires Celery to be running).
`process_images_sync` processes everything immediately in the terminal, which is simpler for
one-off imports when Celery is not set up.

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
