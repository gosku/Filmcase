# ADR 003 — Dual install modes: SQLite + sequential vs PostgreSQL + Celery

**Status**: Accepted
**Date**: 2026-04-11

---

## Context

The project requires a full infrastructure stack — PostgreSQL, RabbitMQ, and Celery — to
support parallel image processing. This is the right choice for large collections and
development workflows, but it is a significant barrier for users who want to browse and
manage a personal library without running database servers and message brokers.

Two usecases depend on the worker stack:

- **`import_images_from_folder`** — scans a folder and enqueues one Celery task per image to
  extract EXIF data and persist the recipe.
- **`generate_thumbnails_for_all_images`** — iterates every image in the database and enqueues
  one Celery task per image to resize and cache a thumbnail.

Key findings:

1. **SQLite is safe for sequential processing.** The existing `process_images_sync` management
   command already demonstrated that running these operations in the calling process, one at a
   time, works correctly with SQLite. The sequencing avoids the write-lock contention that
   makes SQLite incompatible with concurrent Celery workers.

2. **The single-writer queue pattern was ruled out.** A pattern sometimes proposed for SQLite
   compatibility is to parallelise the CPU/IO-bound work across threads while funnelling all
   database writes through a single dedicated writer thread:

   ```
   worker 1 ──┐
   worker 2 ──┼──▶  in-memory queue  ──▶  single writer thread  ──▶  SQLite file
   worker 3 ──┘
   ```

   The parallelism is real but partial. `process_image` would have two phases: reading EXIF data via
   an `exiftool` subprocess (~50 ms, I/O-bound — this is the bottleneck and parallelises well)
   and three sequential DB writes (microseconds, serialised through the writer). The writer
   drains faster than workers produce, so the queue does not back up. In theory the speedup
   approaches the thread count.

   This was ruled out for the following reasons:
   - **Requires splitting the domain operation.** `process_image` would need to be split into
     a read-only phase that returns a plain dataclass and a DB-persist phase. This split is not
     motivated by the domain — it exists solely to work around SQLite's write limitation. Any
     future usecase over the collection would be forced into the same split-phase pattern for
     the same reason.

   - **Not reusable.** Each new usecase would need its own thread pool and queue coordinator,
     or the coordinator grows into a bespoke mini task queue maintained by the project. Neither
     outcome is desirable when a first-class solution already exists.

   - **Does not protect against web server contention.** The web server (`runserver`) is a
     separate OS process with no knowledge of the import's writer thread. Web requests that
     write — rating an image, naming a recipe — go directly to SQLite and compete for the same
     OS-level file lock. To eliminate that contention, every write in the entire application
     would need to be routed through the same coordinator, making it a system-wide write
     serialiser for all of Django, not a localised import optimisation.

   - **Locking under load.** While an import holds a write transaction, any web request that
     tries to write will block waiting for the lock. If SQLite's `busy_timeout` expires before
     the lock is released, the request raises `OperationalError: database is locked` and
     returns a 500 to the user. WAL mode does not help here — WAL allows concurrent reads, not
     concurrent writers from different processes.

   - **Durability.** If the process crashes while items are in the queue, workers have already
     read EXIF data and pushed results, but the queue is RAM-only. On restart everything in it
     is lost with no record of which images made it to SQLite — a full re-scan and diff against
     the DB would be needed. Celery with RabbitMQ handles this: tasks are persisted in the
     broker and survive restarts.

3. **Performance is acceptable for personal use.** At ~50 ms per image, a 5 000-image library
   takes ~4 minutes sequentially. Most personal collections fall in this range.

---

## Options considered

### Option A — Keep a single full-stack install (status quo)

No change. Every user installs PostgreSQL, RabbitMQ, and Celery.

**Why not chosen:** The setup friction is unnecessary for users who only want to browse their
own library. A working single-user install requires three background services that provide no
benefit at that scale.

### Option B — Dual mode with a `USE_ASYNC_TASKS` settings flag ✓ chosen

Add a boolean setting `USE_ASYNC_TASKS` (default `True`) that controls dispatch at the
usecase layer:

- `True` → enqueue Celery tasks (full stack behaviour, unchanged)
- `False` → execute operations sequentially in the calling process (SQLite-safe)

The Makefile exposes two installation targets:

- `make setup-lite` — writes a SQLite env file (`USE_ASYNC_TASKS=False`) and runs migrations.
  No OS services required.
- `make setup-full` — uses the full settings defaults (PostgreSQL, Celery). Requires running
  `./setup.sh` first to install OS-level dependencies.

### Option C — Migrate both installs to `django-tasks`

`django-tasks` (the reference implementation of DEP 0014) provides a unified `enqueue()` API
with swappable backends: `ImmediateBackend` (sequential, in-process) and `DatabaseBackend`
(persistent queue, parallel workers). This would eliminate the `USE_ASYNC_TASKS` flag
entirely — the backend selection in settings would be the only branching point.

**Why deferred:** `django-tasks` was still maturing as of early 2026. Migrating the full
install to `DatabaseBackend` in isolation gives no benefit over the current Celery setup while
adding migration risk. The right time to adopt it is when building out the lite install and
both stacks can be updated together.

---

## Decision

Implement **Option B**: dual install mode controlled by `USE_ASYNC_TASKS`.

The setting name is intentionally generic — it describes the deployment mode, not a specific
usecase. Any future usecase that dispatches work to the worker reads the same flag.

---

## Rationale

| Criterion                                 | Full stack only | Dual mode (chosen) | django-tasks |
| ----------------------------------------- | --------------- | ------------------ | ------------ |
| No infrastructure for personal use        | ✗               | ✓                  | ✓            |
| Parallel processing for large collections | ✓               | ✓ (full mode)      | ✓            |
| Adds bespoke concurrency code             | —               | ✗                  | ✗            |
| Requires new dependency                   | —               | ✗                  | ✓            |
| Unified task API                          | —               | ✗                  | ✓            |
| Risk of migrating mature Celery setup     | —               | ✗                  | ✓            |

---

## Consequences

- `USE_ASYNC_TASKS: bool = True` added to `src/config/settings.py`.
- The `process_images_sync` management command is deleted. Its functionality is now the
  `USE_ASYNC_TASKS=False` branch of `import_images_from_folder`.
- `make setup-lite` writes a minimal env file with `DB_ENGINE=sqlite3` and
  `USE_ASYNC_TASKS=False` and runs migrations. No OS services are installed.
- `make setup-full` retains the previous `make setup` behaviour and requires `./setup.sh` to
  have been run first.
- The `django-tasks` migration is deferred until both install modes adopt it simultaneously.

---

## Runtime requirements by mode

| Component         | Full stack (`make setup-full`) | Lite install (`make setup-lite`) |
| ----------------- | ------------------------------ | -------------------------------- |
| Database          | PostgreSQL                     | SQLite (file)                    |
| Broker            | RabbitMQ                       | —                                |
| Worker            | Celery (`make worker`)         | —                                |
| `USE_ASYNC_TASKS` | `True`                         | `False`                          |
| Import speed      | Parallel (N workers)           | Sequential (1 at a time)         |
