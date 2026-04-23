from __future__ import annotations

import attrs

from src.data import models


@attrs.frozen
class UploadedFile:
    """Carries the raw bytes of an uploaded image together with its original filename."""

    name: str
    content: bytes


@attrs.frozen
class ImportRecipesResult:
    imported: tuple[models.FujifilmRecipe, ...]
    failed: tuple[str, ...]  # original filenames that could not be processed
