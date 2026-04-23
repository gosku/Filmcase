import os
import tempfile

from src.data import models
from src.domain.images.queries import NoFilmSimulationError
from src.domain.recipes import dataclasses as recipe_dataclasses
from src.domain.recipes import operations


def import_recipes_from_uploaded_files(
    *, files: list[recipe_dataclasses.UploadedFile]
) -> recipe_dataclasses.ImportRecipesResult:
    """Extract a models.FujifilmRecipe from each uploaded file's EXIF data.

    For each file the bytes are written to a temporary file under /tmp/,
    the recipe is extracted, and the temporary file is deleted immediately
    afterwards — whether the operation succeeds or fails.

    Files that do not contain Fujifilm recipe EXIF data are recorded as
    failures; processing continues with the remaining files.

    Returns an ImportRecipesResult describing which files were imported
    and which failed.
    """
    imported: list[models.FujifilmRecipe] = []
    failed: list[str] = []

    for file in files:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", dir="/tmp/", delete=False) as tmp:
                tmp.write(file.content)
                tmp_path = tmp.name
            recipe = operations.get_or_create_recipe_from_filepath(filepath=tmp_path)
            imported.append(recipe)
        except NoFilmSimulationError:
            failed.append(file.name)
        finally:
            if tmp_path is not None:
                os.unlink(tmp_path)

    return recipe_dataclasses.ImportRecipesResult(
        imported=tuple(imported),
        failed=tuple(failed),
    )
