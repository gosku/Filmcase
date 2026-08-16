# Documentation Index

## Functionality

- [Web Interface](web_interface.md) — library folder management, image gallery, image detail, recipe explorer, recipe detail, and recipe graphs
- [Management Commands](management_commands.md) — syncing the library, importing images, bulk rating, thumbnails, camera inspection, recipe comparison

## Reference

- [Library Sync](library_sync.md) — how make start scans library folders, deduplicates against the catalog, and uses timestamps to skip unchanged directories
- [EXIF Mapping](exif_mapping.md) — how Fujifilm EXIF fields map to database model fields
- [Recipe Naming](recipe_naming.md) — how recipes are named and the constraints inherited from the camera
- [Recipe Graphs](recipe_graphs.md) — the film simulation graph and version-line graph views, and how to read node distance
- [Image Matching](favorite_image_matching.md) — how images are matched to the catalogue when rating in bulk
- [PTP Encodings](ptp_encodings.md) — PTP/USB encoding reference for camera communication

## Development

- [Contributing](contributing.md) — testing strategy, local environment setup, PR requirements, and review conventions

## Troubleshooting

- [Camera USB Access on Linux](camera_usb_access.md) — fixing "Resource busy" errors and udev setup

## Architecture

- [ADR 001 — Camera Bridge](ADRs/001-camera-bridge.md) — decision to use PyUSB with raw PTP/USB for camera communication
- [ADR 002 — Recipe Relationship Graph](ADRs/002-recipe-relationship-graph.md) — graph definition, topology decisions, and the two complementary views
- [ADR 003 — Dual Install Modes](ADRs/003-dual-install-modes.md) — SQLite + sequential vs PostgreSQL + Celery, and why a single-writer queue pattern was ruled out
- [ADR 004 — Recipe Import File Picker](ADRs/004-recipe-import-file-picker.md) — browser file upload over native dialog or Tauri, and which layer owns the tempfile
- [ADR 005 — Recipe Sharing via Image Cards](ADRs/005-recipe-sharing-via-image-cards.md) — recipe sharing via image cards with embedded QR codes
- [ADR 006 — QR Decode Library and Minimum QR Code Size](ADRs/006-qr-decode-library-and-size.md) — QR decode library choice and minimum QR code size
- [ADR 007 — Normalize Recipe Data Before Storage](ADRs/007-normalize-recipe-data.md) — normalizing recipe data before storage
- [ADR 008 — Recipe Versioning via Generalised Grouping](ADRs/008-recipe-versioning.md) — version lines and recipe families via a shared grouping abstraction
- [ADR 009 — Moving a Recipe Between Version Lines](ADRs/009-move-recipe-between-version-lines.md) — reassigning an existing recipe to a different VERSION_LINE group while keeping positions contiguous
- [ADR 010 — Image Library: Folder Monitoring and Catalog Sync](ADRs/010-image-library.md) — persisting monitored folders and detecting and importing new images automatically at startup
- [ADR 011 — Library Sync on Folder Add/Update](ADRs/011-library-sync-on-folder-change.md) — triggering a single-folder sync from the Library page with server-side, DB-backed progress in both install modes
- [ADR 012 — Pluggable Card Designs](ADRs/012-pluggable-card-designs.md) — a CardDesign abstraction replacing the flat CardTemplate, enabling fundamentally different card layouts (supersedes ADR 005's composition model)
- [ADR 013 — Library Sync Removes Missing Images](ADRs/013-library-sync-removes-missing-images.md) — removing catalog entries whose files are gone, telling a move apart from a deletion, and the guard against a mass wipe (supersedes ADR 010's add-only sync and mtime gating, and ADR 011's removal and rescan decisions)
- [ADR 014 — Remembering Images That Cannot Be Imported](ADRs/014-remembering-images-that-cannot-be-imported.md) — recording files the sync cannot import so they are not re-examined on every run, and batching worker dispatch so a large import does not block startup
- [ADR 015 — Cleaning Up After a Folder Path Change](ADRs/015-cleaning-up-after-a-folder-path-change.md) — removing images stranded outside a library folder when its path narrows, without breaking the relocation a moved folder depends on
