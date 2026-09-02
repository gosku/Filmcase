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

**Skipped directories.** Directories whose name starts with any of the prefixes in
`LIBRARY_IGNORED_DIRECTORY_PREFIXES` are pruned from the walk entirely: nothing inside them is
read, imported, or recorded as ignored. The default set covers machine-generated folders that
never hold your photos, such as Synology `@eaDir` thumbnail caches, QNAP `@Recycle`, Windows
`$RECYCLE.BIN` and `System Volume Information`, and hidden dot-directories. The same rule is
used by the folder browser when you pick a folder to add. Edit the prefixes on Settings >
Preferences > Library. The match is a plain prefix, so `@` also hides a folder you named
`@work`.

**Deduplication across overlapping folders.** If two registered folders overlap (for example,
`/Photos` and `/Photos/2024`), a file discovered in the first folder is not processed again
when the second folder is scanned. The command tracks every path seen so far across the whole
run and excludes it from subsequent folders.

**Missing folders.** If a registered folder is no longer present on disk, the command records
it as missing, updates its last-checked timestamp, and moves on to the next folder. The
missing path is reported in the command output and does not abort the sync. **Nothing is
removed from the gallery in this case**, because an unplugged drive looks exactly like a folder
whose photos were all deleted, and the safe reading is that the drive will come back.

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
Removing a folder asks what you want to happen to its images: you can keep them in the gallery
or take them out along with the folder. Either way the photo files themselves stay on disk.

The triggered sync reuses the same per-folder scan described above and behaves according to
your install mode:

- **Lite install:** the sync runs in a background thread, so the page responds immediately
  while images are imported behind the scenes. You can navigate away and come back; the work
  keeps running on the server.
- **Full install:** the new images are enqueued to the Celery worker and the page returns at
  once. If no worker is reachable, the folder is still added but a message explains that it
  could not be synced (start a worker with `make worker`, then re-add or re-save the folder).

Changing a folder's path rescans the whole new location. If you moved the folder rather than
pointing it somewhere new, the photos inside it are recognised and simply follow the move; you
do not lose ratings or favourites. Progress appears live in the folder's **Sync** column.

If the new path is *narrower* than the old one, say you change `/Photos` to `/Photos/2024`, the
photos that fall outside it are no longer in any library folder, so the next sync takes them out of
the gallery. Their files are untouched: widen the folder again and they are imported back. The
Library page says how many left for this reason, and the safety guard applies, so a drastic
narrowing is reported rather than applied until you re-run with `--force-prune`.

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

## Removing images that disappeared

The sync keeps the gallery in step with your folders in both directions. When a photo is no
longer where the catalog expects it, its entry is taken out of the gallery.

**Filmcase never deletes your photo files.** "Removing" an image only removes Filmcase's record
of it. Every file stays on disk exactly where it is. The only case where a photo leaves the
gallery is the case where you already deleted or moved the file yourself.

**Moves and renames are not removals.** If you rename a photo, move it into another subfolder,
rename a whole subfolder, or move a photo from one library folder to another, Filmcase
recognises the file by its contents and simply updates where it is. The photo keeps its
rating, its favourite mark and its album membership. Nothing is lost and nothing is
re-imported.

The distinction is made by looking at the old location: if the file is no longer there, the
photo moved. If it is still there, you made a copy, and the copy does not become a second
entry.

**Ordering.** Everything new is imported before anything is removed, so a photo that moved has
already been re-linked by the time removal is considered.

### The safety guard

Removal is permanent, and "the file is missing" is ambiguous: an external drive that is not
plugged in, a network share that has not mounted, or a folder that has become unreadable all
look identical to "every photo in here was deleted".

The guard ships **disabled**, so removals always apply. It is off because the only way past one
that has tripped is `sync_library --force-prune`, and the Library page offers no equivalent: a
guard firing on a folder you just repointed would leave the gallery stale with nothing on that
page able to fix it. Set `LIBRARY_PRUNE_GUARD_FRACTION` and `LIBRARY_PRUNE_GUARD_MIN_IMAGES` to
real thresholds (0.5 and 20, say) to turn it on.

Once enabled, a sync that would remove more than that share of a folder's images, **and** more
than that many of them, removes nothing and tells you instead:

```
Skipped removing 340 of 512 image(s) in /Volumes/Photos (safety guard). That usually means a
drive is not mounted rather than that the photos were deleted. Re-run with --force-prune to
remove them anyway.
```

The same warning appears on the Library page against that folder. Both thresholds have to be
crossed, so ordinary cleanups (emptying a folder of a handful of photos) are applied without
any fuss.

### Controlling removal from the command line

```sh
python manage.py sync_library --dry-run-prune   # list what would go, remove nothing
python manage.py sync_library --force-prune     # remove even if the guard would stop it
python manage.py sync_library --no-prune        # import only, never remove
```

In full install mode the removal happens in the Celery worker after the command has exited, so
the command's own count is always zero; watch the Library page for the result.

## Removing a folder from the Library

Pressing **Remove** on a folder asks what should happen to its images. It tells you how many
images in the gallery come only from that folder, and offers two choices:

- **Remove folder only** stops monitoring the folder and leaves its images in the gallery.
- **Remove folder and its images** also takes those images out of the gallery.

Again, no photo file is deleted either way.

If folders are nested (say both `/Photos` and `/Photos/2024` are registered), removing the
inner one never takes images the outer one still monitors. Only images that come *exclusively*
from the folder you are removing are counted, and only those can go.

## Files the sync cannot import

Not every JPEG in a library folder can be imported. Photos from another camera carry no Fujifilm
recipe, and occasionally a file fails outright. Filmcase remembers those files instead of
re-reading them on every sync.

**Nothing is deleted or changed.** An ignored file was never in the gallery to begin with; the
record only means the sync stops looking at it. Your files stay on disk exactly where they are.

Why it matters: reading a photo's metadata costs a separate `exiftool` process. On a library with
15,000 non-Fujifilm JPEGs, re-examining them on every startup is 15,000 processes to reach the same
conclusion as last time.

**A file you fix comes back on its own.** Each record stores the file's size and modification time
as they were when it was examined. If either changes, the file is examined again automatically, so
re-exporting a photo with proper EXIF at the same path is enough. Nothing needs clicking.

### Seeing and undoing it

Each folder row in the Library page shows how many of its files are ignored, linking to a page that
lists them with the reason and, for failures, the error. Filter by reason to find the handful of
real errors among the many "not a Fujifilm photo" entries.

From there you can retry a single file, retry every error at once, or retry everything. Retrying an
unchanged non-Fujifilm file does nothing, since it will be read and rejected again; the page says so
on each such row.

From the command line:

```sh
python manage.py sync_library --retry-failed   # examine every ignored file again
```

Expect that run to be slow: examining them again is exactly the cost the records avoid.

## Why a large import no longer blocks startup

In full install mode the sync hands images to the Celery worker, and it cannot return until every
message has been published. One message per file meant a large import held up `make start` for as
long as publishing took: on tens of thousands of files, tens of seconds before the server was even
reachable.

Images are now sent in batches, so the message count falls by the batch size (`SYNC_IMAGE_BATCH_SIZE`,
100 by default). Each image is still processed and counted individually, so progress in the Sync
column is unchanged.

Note that changing this required a new worker task, so **restart your Celery worker once** after
upgrading (`make worker`).
