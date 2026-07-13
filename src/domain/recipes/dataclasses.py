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
    """
    The outcome of importing a batch of files, one entry per file.

    Importing a file does not necessarily add a recipe: the recipe it carries
    is matched against the library by its settings, and may already be there.
    So a successfully imported file lands in ``imported``, and additionally in
    ``created`` if it added a recipe to the library, or in ``updated`` if it
    completed a recipe that was already there by giving it a name.

    A file that matched an existing recipe and had nothing to add appears only
    in ``imported``. Two files carrying the same recipe both appear, so these
    are counts of files, not of distinct recipes.

    Only the QR-card import can tell these apart. The import that reads
    recipes out of image EXIF leaves ``created`` and ``updated`` empty.

    :param imported: recipes read successfully, one per file.
    :param failed: filenames that could not be read.
    :param created: recipes that were new to the library.
    :param updated: recipes that were already in the library and got named.
    """

    imported: tuple[models.FujifilmRecipe, ...]
    failed: tuple[str, ...]
    created: tuple[models.FujifilmRecipe, ...] = ()
    updated: tuple[models.FujifilmRecipe, ...] = ()
