from __future__ import annotations

import enum

import attrs

from src.data import models


class RecipeImportOutcome(enum.Enum):
    """
    What an import did to the library for one incoming recipe.

    A recipe arriving from a shared card is matched against the existing
    library by its settings, so importing it does not necessarily create
    anything.
    """

    CREATED = "created"
    NAME_BACKFILLED = "name_backfilled"  # matched an existing recipe that had no name
    UNCHANGED = "unchanged"  # matched an existing recipe; nothing to add


@attrs.frozen
class UploadedFile:
    """
    Carries the raw bytes of an uploaded image together with its original filename.
    """

    name: str
    content: bytes


@attrs.frozen
class ImportRecipesResult:
    imported: tuple[models.FujifilmRecipe, ...]
    failed: tuple[str, ...]  # original filenames that could not be processed
