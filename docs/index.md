# Documentation Index

## Using Filmcase

- [User Guide](user_guide.md) — everything you can do from the web app and the command line
  - [1 Library](user_guide.md#1-library)
    - [1.1 Managing folders](user_guide.md#11-managing-folders)
    - [1.2 Files that could not be imported](user_guide.md#12-files-that-could-not-be-imported)
    - [1.3 Automatic sync on startup](user_guide.md#13-automatic-sync-on-startup)
  - [2 Images](user_guide.md#2-images)
    - [2.1 Gallery](user_guide.md#21-gallery)
    - [2.2 Image Detail](user_guide.md#22-image-detail)
  - [3 Recipes](user_guide.md#3-recipes)
    - [3.1 Explorer](user_guide.md#31-explorer)
    - [3.2 Importing, creating & deleting recipes](user_guide.md#32-importing-creating--deleting-recipes)
    - [3.3 Recipe Detail](user_guide.md#33-recipe-detail)
    - [3.4 Graph](user_guide.md#34-graph)
  - [4 Management Commands](user_guide.md#4-management-commands)
    - [4.1 Running commands](user_guide.md#41-running-commands)
    - [4.2 Syncing the library](user_guide.md#42-syncing-the-library)
    - [4.3 Importing images](user_guide.md#43-importing-images)
    - [4.4 Rating images in bulk](user_guide.md#44-rating-images-in-bulk)
    - [4.5 Pre-generating thumbnails](user_guide.md#45-pre-generating-thumbnails)
    - [4.6 Inspecting camera slots](user_guide.md#46-inspecting-camera-slots)
    - [4.7 Comparing recipes](user_guide.md#47-comparing-recipes)

## How It Works

- [Library Sync](library_sync.md) — how make start scans library folders, deduplicates against the catalog, and uses timestamps to skip unchanged directories
- [Recipe Naming](recipe_naming.md) — how recipes are named and the constraints inherited from the camera
- [Image Matching](favorite_image_matching.md) — how images are matched to the catalogue when rating in bulk
- [EXIF Mapping](exif_mapping.md) — reference tables mapping Fujifilm EXIF fields to database model fields
- [PTP Encodings](ptp_encodings.md) — reference for the PTP/USB property codes used to talk to the camera

## Installation & Setup

- [Manual Installation](manual_install.md) — installing the dependencies and setting up the project by hand, without the setup script
- [Running in Docker](docker.md) — the containerised full stack, HTTPS with a self-signed certificate, mounting photo directories, and what camera access can and cannot do in a container
- [Pushing Recipes from the Browser](camera_webusb.md) — driving the camera from your own machine over WebUSB, for installs where Filmcase runs somewhere you do not sit

## Troubleshooting

- [Camera USB Access on Linux](camera_usb_access.md) — fixing "Resource busy" errors and udev setup, for both the server-side and browser-side transports

## Development

- [Contributing](contributing.md) — testing strategy, local environment setup, PR requirements, and review conventions

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
- [ADR 016 — Client-side Camera Transport](ADRs/016-client-side-camera-transport.md) — moving the PTP transport into the browser over WebUSB so a headless install can still push recipes, and how the two implementations are kept from diverging (extends ADR 001)
- [ADR 017 — Skipping Directories by Name Prefix](ADRs/017-skipping-directories-by-name-prefix.md) — a configurable list of directory-name prefixes both library walks prune from the scan entirely, keeping Synology `@eaDir` and other machine-generated folders out of the catalog and the ignored-files page
