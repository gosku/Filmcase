# ADR 010 — Image Library: folder monitoring and catalog sync

**Status**: Accepted
**Date**: 2026-06-28

---

## Context

The app imports images by having the user run `make import PATH=...` against a specific folder. There is no persistent record of which folders the user's photo collection lives in, and there is no mechanism for the app to detect new photos on its own. Every import is fully manual and requires the user to know which command to run.

The goal is to allow the app to maintain a live catalog: the user registers their photo folders once, and from then on the app detects and imports new images automatically at startup.

---

## Problem

Two distinct problems need solving:

1. **Persistence**: where does the app store which folders to monitor?
2. **Detection**: given a folder (or folder tree) that may contain tens of thousands of images, how does the app efficiently find only the new files when one or a few are added?

---

## Decision

### The Library model

Introduce a `LibraryFolder` table. Each row records one folder the app monitors. Fields: `path` (normalized absolute path, unique), `created_at`, `updated_at`, `last_processed_at` (last time a new image was imported from this folder), `last_checked_at` (last time the folder was scanned, whether or not new files were found).

Users manage the list through a web UI that includes a filesystem browser backed by an HTMX endpoint. No command-line knowledge is required after initial setup.

### Normalized absolute paths

`LibraryFolder.path` always stores a normalized absolute path. The registration step resolves any input form:
- `~` is expanded via `os.path.expanduser()`
- relative paths are resolved via `Path.resolve()`

This ensures the stored value is unambiguous regardless of how or from where the app is started. The normalization happens in the domain operation, before the row is written.

### Startup sync (not live monitoring)

Rather than a persistent file-watcher daemon, the app syncs at startup. `make start` runs `manage.py sync_library` to completion before starting the web server. This approach:

- Works in both lite mode (SQLite, no Celery) and full mode (PostgreSQL + Celery) without platform-specific code.
- Requires no daemon supervision or restart handling.
- Is transparent to the user: `make start` is a single command.
- In full mode, tasks are enqueued (fast); in lite mode, processing is synchronous (acceptable for a single-user local app).

Live monitoring via `inotify`/`watchdog` was considered but deferred: it requires a persistent daemon and a catch-up sync pass on restart anyway. The startup sync covers the same practical need without the operational overhead.

### Detection algorithm

The sync uses a two-level algorithm:

**Level 1 — directory classification (cheap)**

Walk the directory tree under each library folder. For each directory, stat its mtime and classify it into one of three buckets:

- **Unseen**: no `Image.filepath` has this directory as a parent. Every file inside is new -- no per-file DB query needed.
- **Changed**: the app has seen this directory before, but `mtime > last_checked_at`. Some files may be new; check at file level.
- **Unchanged**: `mtime <= last_checked_at`. Skip entirely.

Known directories are derived from `Image.filepath` using Python-side `os.path.dirname()` extraction after a single DB query. A DB-side approach (PostgreSQL `regexp_replace`, SQLite string functions) would require two different SQL expressions for the two supported backends; Python extraction is simpler and equally fast at the scale of this app.

**Level 2 — file-level check (only for changed directories)**

For changed directories, list their files and query the DB for the ones already known:

```python
candidate_files = list_files_in_changed_dirs()
known_in_candidates = set(
    Image.objects.filter(filepath__in=candidate_files).values_list("filepath", flat=True)
)
new_paths = files_in_unseen_dirs | (set(candidate_files) - known_in_candidates)
```

Only `new_paths` are handed to `process_image`. No SHA-256 hashing until a file is confirmed new.

**First-run behavior**

When `last_checked_at` is null (first sync), every directory is classified as unseen. The algorithm degrades gracefully to "process everything" without a special code path.

**Pre-existing images**

The app already has `Image` records imported before the Library concept existed. Pre-existing filepaths that live under a registered library folder appear in the known-paths set and are correctly skipped. Pre-existing filepaths outside any library folder are irrelevant to the walk and have no effect on the algorithm.

**Important**: the Library is a monitoring concept, not the catalog boundary. Images imported before the Library existed remain in the DB and remain accessible. The sync only ever adds -- it never removes.

---

## Options considered

### Option A — inotify / watchdog (live monitoring)

Register OS-level file watchers on all subdirectories. The kernel notifies the app the moment a file is created or moved in.

**Why not chosen**: requires a persistent daemon. If the watcher is down, events are lost and a catch-up scan is needed anyway. `inotify` has a kernel limit on watched directories. Adds operational complexity disproportionate to a single-user personal app.

### Option B — full table scan on every startup

Load all 50K `Image.filepath` values, walk all library folders, compute the set difference.

**Why not chosen as the primary approach**: correct but wasteful. The two-level mtime + DB algorithm avoids per-file work for unchanged directories. The full scan is the fallback for the first run only.

### Option C — denormalized `dirpath` field on `Image`

Store the parent directory as a separate indexed field to make the "known directories" query O(1) instead of O(n) with Python extraction.

**Why deferred**: Python extraction of parent directories from the existing `filepath` field is fast enough at current scale (~50K images). The denormalized field can be added later if profiling shows it matters.

---

## Consequences

- `LibraryFolder` is a monitoring list, not a hard boundary on the catalog. Removing a folder from the library stops monitoring it but does not delete its images.
- `last_checked_at` must be reliably updated after every sync pass for the mtime optimisation to work correctly.
- The filesystem browser endpoint exposes the server's directory tree. This is acceptable because the app is single-user and the server and the user's machine are the same host.
