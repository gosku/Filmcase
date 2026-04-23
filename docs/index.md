# Documentation Index

## Functionality

- [Web Interface](web_interface.md) — image gallery, image detail, recipe explorer, recipe detail, and recipe graphs
- [Management Commands](management_commands.md) — importing images, bulk rating, thumbnails, camera inspection, recipe comparison

## Reference

- [EXIF Mapping](exif_mapping.md) — how Fujifilm EXIF fields map to database model fields
- [Recipe Naming](recipe_naming.md) — how recipes are named and the constraints inherited from the camera
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

