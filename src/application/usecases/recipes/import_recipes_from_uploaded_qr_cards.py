import os
import tempfile

from src.data import models
from src.domain.images import events
from src.domain.recipes import dataclasses as recipe_dataclasses
from src.domain.recipes import operations
from src.domain.recipes.cards.queries import (
    InvalidQRRecipePayloadError,
    QRCodeNotFoundError,
)


def import_recipes_from_uploaded_qr_cards(
    *, files: list[recipe_dataclasses.UploadedFile]
) -> recipe_dataclasses.ImportRecipesResult:
    """Extract a FujifilmRecipe from the QR code on each uploaded card image.

    For each file the bytes are written to a temporary file under /tmp/, the
    QR code is decoded and the recipe extracted, and the temporary file is
    deleted immediately afterwards — whether the operation succeeds or fails.

    Files from which no QR code can be decoded, or whose QR carries an
    invalid payload, are recorded as failures; processing continues with the
    remaining files. Each failure is also published as an event so the
    reason is visible in the dev terminal and the events log file.
    """
    imported: list[models.FujifilmRecipe] = []
    failed: list[str] = []

    for file in files:
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", dir="/tmp/", delete=False) as tmp:
                tmp.write(file.content)
                tmp_path = tmp.name
            recipe = operations.get_or_create_recipe_from_qr_card(filepath=tmp_path)
            imported.append(recipe)
        except QRCodeNotFoundError:
            failed.append(file.name)
            events.publish_event(
                event_type=events.RECIPE_IMPORT_QR_CARD_FAILED,
                filename=file.name,
                failure_reason="qr_not_found",
            )
        except InvalidQRRecipePayloadError as exc:
            failed.append(file.name)
            events.publish_event(
                event_type=events.RECIPE_IMPORT_QR_CARD_FAILED,
                filename=file.name,
                failure_reason=exc.reason,
            )
        finally:
            if tmp_path is not None:
                os.unlink(tmp_path)

    return recipe_dataclasses.ImportRecipesResult(
        imported=tuple(imported),
        failed=tuple(failed),
    )
