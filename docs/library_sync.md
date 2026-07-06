# Library Sync

When you run `make start`, Filmcase automatically scans your registered library folders for
new images before the web server comes up. This document explains how that process works.

## How make start triggers a sync

`make start` is a two-step Makefile target. It first runs the `sync_library` management
command, then starts the Django development server with `make run`. If the sync command fails
(for example, because no Celery worker is reachable in full install mode), it prints a warning
and the server still starts.

## What the sync does

The sync command works through your registered library folders one at a time.

**Loading the catalog snapshot.** Before touching the filesystem, the command reads the
complete set of image file paths already in the database into memory. This single query
becomes the reference point for the entire sync run.

**Scanning each folder.** For each registered library folder, the command walks the directory
tree recursively and collects all JPEG files found. It then computes the set difference
between the discovered paths and the catalog snapshot: only files not yet in the catalog are
processed. This means re-running the command is always safe; existing entries are never
duplicated or overwritten.

**Deduplication across overlapping folders.** If two registered folders overlap (for example,
`/Photos` and `/Photos/2024`), a file discovered in the first folder is not processed again
when the second folder is scanned. The command tracks every path seen so far across the whole
run and excludes it from subsequent folders.

**Missing folders.** If a registered folder is no longer present on disk, the command records
it as missing, updates its last-checked timestamp, and moves on to the next folder. The
missing path is reported in the command output and does not abort the sync.

**Processing new files.** New images are handled according to your install mode:

- **Lite install** (`USE_ASYNC_TASKS=False`): each file is processed inline, one at a time,
  before the command exits. Files without Fujifilm EXIF data (for example, JPEGs from other
  camera brands) are skipped and counted separately.
- **Full install** (`USE_ASYNC_TASKS=True`): a Celery task is enqueued for each new file.
  The command exits as soon as all tasks are queued; actual processing happens in parallel
  across the worker pool. If no Celery worker responds to a ping at the start of the sync,
  the entire sync is skipped with a warning.

## Syncing from the Library page

You no longer have to restart the app to pick up a newly registered folder. Adding a folder,
or changing an existing folder's path, triggers a sync of that one folder straight away.
Removing a folder does not trigger anything: it only stops the folder being monitored and
never deletes images that were already imported.

The triggered sync reuses the same per-folder scan described above and behaves according to
your install mode:

- **Lite install:** the sync runs in a background thread, so the page responds immediately
  while images are imported behind the scenes. You can navigate away and come back; the work
  keeps running on the server.
- **Full install:** the new images are enqueued to the Celery worker and the page returns at
  once. If no worker is reachable, the folder is still added but a message explains that it
  could not be synced (start a worker with `make worker`, then re-add or re-save the folder).

Changing a folder's path also clears its last-checked timestamp, so the whole new location is
rescanned from scratch. Progress appears live in the folder's **Sync** column (see below).

## Timestamp-based directory gating

For large collections, walking every subdirectory on every startup would be slow. To avoid
that, the sync uses filesystem modification times to skip directories that cannot have changed.

Each library folder in the database records a `last_checked_at` timestamp, set at the end of
every sync pass. Before listing the files inside a directory during a walk, the sync compares
that directory's modification time against `last_checked_at`. If the directory's modification
time is at or before the last check time, the directory is skipped entirely. Adding a file to
a directory updates that directory's modification time, so any directory that has received new
files since the last check is always included.

This gating applies independently to each directory in the tree. If a parent directory has
not changed but one of its subdirectories has, the subdirectory is still scanned. The result
is that the second `make start` after an initial import typically does very little work, even
if the library spans thousands of files across many folders.

## Timestamps shown in the Library page

Each folder row in the Library page shows two timestamps:

- **Last Checked** -- the most recent time the sync examined this folder, regardless of
  whether anything new was found.
- **Last Synced** -- the most recent time the sync actually imported or enqueued new images
  from this folder. This stays blank until at least one new file is found.

The **Sync** column shows the status of the most recent sync for each folder: `Scanning...`
while the folder is being walked, a progress bar while images are imported, and a final
summary such as `Imported 36, skipped 3` when it finishes. While a sync is active, the column
refreshes on its own every couple of seconds, so you can watch it progress without reloading
the page.
