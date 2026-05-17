from __future__ import annotations

import attrs
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import aggregates
from django.utils import timezone
from src.data import models
from src.domain.images import dataclasses as image_dataclasses
from src.domain.images import events
from src.domain.images import queries as image_queries
from src.domain.recipes import normalization as recipe_normalization
from src.domain.recipes import queries as recipe_queries
from src.domain.recipes import validation as recipe_validation
from src.domain.recipes.cards import operations as card_operations
from src.domain.recipes.cards import queries as card_queries


def _parse_numeric(*, s: str | None) -> Decimal | None:
    """
    Convert a signed numeric string like '+4', '-1.5', '0' to Decimal, or None.

    Decimal is used (not float or int) so that half-step values like -1.5 and
    +0.5 are stored exactly in the DecimalField without rounding.
    """
    if s is None or s == "N/A":
        return None
    return Decimal(s)


def _settings_values_equal(field: str, a: object, b: object) -> bool:
    """
    Compare two FujifilmRecipeData field values for equality.

    Decimal fields may be formatted differently between sources ('+2' from
    recipe_from_db vs '2' from the form), so they are compared as Decimal
    values to avoid false positives in the settings-changing check.
    """
    if field in recipe_queries.DECIMAL_FIELDS:
        try:
            a_dec = Decimal(str(a)) if a is not None else None
            b_dec = Decimal(str(b)) if b is not None else None
            return a_dec == b_dec
        except Exception:  # noqa: BLE001 — fall back to direct comparison on unexpected values
            pass
    return a == b


@attrs.frozen
class VersionLineGroupNotFoundError(Exception):
    """
    Raised when no VERSION_LINE group with the given ID exists.
    """

    group_id: int


@transaction.atomic
def add_recipe_to_version_line(
    *,
    recipe: models.FujifilmRecipe,
    group_id: int | None,
) -> models.RecipeGroupMember:
    """
    Add a newly created recipe to a version line group.

    If *group_id* is None, creates a new VERSION_LINE group and adds the
    recipe as position=1. Otherwise appends the recipe to the given group at
    max(position)+1.

    :raises VersionLineGroupNotFoundError: If no VERSION_LINE group with
        *group_id* exists.
    """
    now = timezone.now()

    if group_id is None:
        group = models.RecipeGroup.new_version_line()
        member = models.RecipeGroupMember.new(
            group=group,
            recipe_id=recipe.pk,
            position=1,
            added_at=now,
        )
    else:
        try:
            group = models.RecipeGroup.objects.get(
                pk=group_id,
                group_type=models.RecipeGroup.GROUP_TYPE_VERSION_LINE,
            )
        except models.RecipeGroup.DoesNotExist:
            raise VersionLineGroupNotFoundError(group_id=group_id)

        result = models.RecipeGroupMember.objects.filter(group=group).aggregate(
            max_position=aggregates.Max("position")
        )
        next_position = (result["max_position"] or 0) + 1
        member = models.RecipeGroupMember.new(
            group=group,
            recipe_id=recipe.pk,
            position=next_position,
            added_at=now,
        )

    events.publish_event(
        event_type=events.RECIPE_ADDED_TO_VERSION_LINE,
        recipe_id=recipe.pk,
        group_id=group.pk,
        position=member.position,
    )
    return member


@transaction.atomic
def get_or_create_recipe_from_data(
    *,
    data: image_dataclasses.FujifilmRecipeData,
    group_id: int | None = None,
) -> tuple[models.FujifilmRecipe, bool]:
    """
    Create or retrieve a FujifilmRecipe for the given recipe data.

    Returns ``(recipe, created)``. Uniqueness is determined by the recipe
    settings only — ``data.name`` is applied via ``defaults`` on the create
    path and is never considered during lookup or written back on the get path.

    When *created* is True, adds the recipe to a version line via
    ``add_recipe_to_version_line``. Pass *group_id* to append
    the new recipe to an existing version line; omit it to start a new one.

    This is the single seam for ``FujifilmRecipe.get_or_create`` — shared by
    every caller that has already produced a FujifilmRecipeData (from EXIF,
    from a QR card, or any future source).
    """
    data = recipe_normalization.normalize_recipe_data(data)
    recipe_validation.validate_recipe_data(data)
    recipe, created = models.FujifilmRecipe.get_or_create(
        film_simulation=data.film_simulation,
        dynamic_range=data.dynamic_range or "",
        d_range_priority=data.d_range_priority,
        grain_roughness=data.grain_roughness,
        grain_size=data.grain_size if data.grain_size is not None else "Off",
        color_chrome_effect=data.color_chrome_effect,
        color_chrome_fx_blue=data.color_chrome_fx_blue,
        white_balance=data.white_balance,
        white_balance_red=data.white_balance_red,
        white_balance_blue=data.white_balance_blue,
        highlight=_parse_numeric(s=data.highlight),
        shadow=_parse_numeric(s=data.shadow),
        color=_parse_numeric(s=data.color),
        sharpness=_parse_numeric(s=data.sharpness),
        high_iso_nr=_parse_numeric(s=data.high_iso_nr),
        clarity=_parse_numeric(s=data.clarity),
        monochromatic_color_warm_cool=_parse_numeric(s=data.monochromatic_color_warm_cool),
        monochromatic_color_magenta_green=_parse_numeric(s=data.monochromatic_color_magenta_green),
        name=data.name,
    )
    if created:
        add_recipe_to_version_line(recipe=recipe, group_id=group_id)
        events.publish_event(
            event_type=events.RECIPE_CREATED,
            recipe_id=recipe.pk,
            film_simulation=recipe.film_simulation,
        )
    else:
        events.publish_event(
            event_type=events.RECIPE_DEDUPLICATED,
            recipe_id=recipe.pk,
            film_simulation=recipe.film_simulation,
        )
    return recipe, created


def get_or_create_recipe_from_metadata(
    *, metadata: image_dataclasses.ImageExifData,
) -> tuple[models.FujifilmRecipe, bool]:
    """
    Create or retrieve a FujifilmRecipe for the given parsed EXIF data.

    :raises NoFilmSimulationError: If the EXIF data contains no known film simulation.
    """
    try:
        recipe_data = image_queries.exif_to_recipe(exif=metadata)
    except KeyError:
        raise image_queries.NoFilmSimulationError()
    return get_or_create_recipe_from_data(data=recipe_data)


def get_or_create_recipe_from_filepath(
    *, filepath: str,
) -> tuple[models.FujifilmRecipe, bool]:
    """
    Read EXIF from *filepath* and return the matching FujifilmRecipe, creating it if needed.

    :raises NoFilmSimulationError: If the file is not a Fujifilm image or has no film simulation.
    """
    metadata = image_queries.read_image_exif(image_path=filepath)
    if metadata.camera_make.upper() != "FUJIFILM":
        raise image_queries.NoFilmSimulationError(filepath)
    return get_or_create_recipe_from_metadata(metadata=metadata)


def get_or_create_recipe_from_qr_card(
    *, filepath: str,
) -> tuple[models.FujifilmRecipe, bool]:
    """
    Decode the QR on a recipe-card image and return the matching FujifilmRecipe.

    :raises QRCodeNotFoundError: If no QR code can be decoded from *filepath*.
    :raises InvalidQRRecipePayloadError: If the decoded content is not a valid
        QRFujifilmRecipe payload.
    """
    qr_recipe = card_queries.get_qr_recipe_from_image(image_path=filepath)
    recipe_data = card_queries.get_recipe_data_from_qr_recipe(qr_recipe=qr_recipe)
    return get_or_create_recipe_from_data(data=recipe_data)


@attrs.frozen
class RecipeNotFoundError(Exception):
    """
    Raised when no recipe with the given ID exists.
    """

    recipe_id: int


@attrs.frozen
class ImageNotFoundError(Exception):
    """
    Raised when no image with the given ID exists.
    """

    image_id: int


@attrs.frozen
class ImageNotAssociatedToRecipeError(Exception):
    """
    Raised when the image is not linked to the recipe.
    """

    recipe_id: int
    image_id: int


def set_cover_image_for_recipe(*, recipe_id: int, image_id: int) -> None:
    """
    Set the cover image of a recipe to the given image.

    Raises:
        RecipeNotFoundError: If no recipe with *recipe_id* exists.
        ImageNotFoundError: If no image with *image_id* exists.
        ImageNotAssociatedToRecipeError: If the image is not linked to the recipe.
    """
    try:
        recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    except models.FujifilmRecipe.DoesNotExist:
        raise RecipeNotFoundError(recipe_id)

    try:
        image = models.Image.objects.get(pk=image_id)
    except models.Image.DoesNotExist:
        raise ImageNotFoundError(image_id)

    if image.fujifilm_recipe_id != recipe_id:
        raise ImageNotAssociatedToRecipeError(recipe_id=recipe_id, image_id=image_id)

    recipe.set_cover_image(image_id=image_id)
    events.publish_event(
        event_type=events.RECIPE_COVER_IMAGE_SET,
        recipe_id=recipe_id,
        image_id=image_id,
    )


@attrs.frozen
class RecipeNameValidationError(Exception):
    """
    Raised when a recipe name fails validation (too long or non-ASCII).
    """

    name: str


def set_recipe_name(*, recipe: models.FujifilmRecipe, name: str) -> None:
    """
    Set the name of *recipe* to *name* after validating it.

    Raises:
        RecipeNameValidationError: If the name is empty, longer than
            RECIPE_NAME_MAX_LEN, or contains non-ASCII characters.
    """
    if not name or len(name) > image_dataclasses.RECIPE_NAME_MAX_LEN or not name.isascii():
        raise RecipeNameValidationError(name)
    recipe.set_name(name=name)
    events.publish_event(
        event_type=events.RECIPE_IMAGE_UPDATED,
        name=name,
        recipe_id=recipe.pk,
    )


@attrs.frozen
class RecipeHasImagesError(Exception):
    """
    Raised when a recipe cannot be deleted because it still has associated Images.
    """

    recipe_id: int
    image_count: int
    name: str


@attrs.frozen
class RecipeCannotBeEditedError(Exception):
    """
    Raised when the settings fields of a recipe cannot be changed because it has associated Images.
    """

    recipe_id: int
    image_count: int
    name: str


@attrs.frozen
class RecipeSettingsConflictError(Exception):
    """
    Raised when updating a recipe would duplicate the settings of an existing recipe.
    """

    recipe_id: int


def update_recipe(*, recipe: models.FujifilmRecipe, data: image_dataclasses.FujifilmRecipeData) -> None:
    """
    Update an existing FujifilmRecipe from the given data.

    Normalises *data* before comparing. Settings fields (film simulation, tone
    curves, etc.) are only written when they differ from the current values and
    the recipe has no associated Images. Metadata fields (name) are always
    writable regardless of image association.

    :raises RecipeCannotBeEditedError: If settings fields changed but the recipe has associated Images.
    :raises RecipeSettingsConflictError: If the new settings would duplicate an existing recipe.
    """
    data = recipe_normalization.normalize_recipe_data(data)
    current_data = recipe_queries.recipe_from_db(recipe=recipe)

    settings_changing = any(
        not _settings_values_equal(field, getattr(data, field), getattr(current_data, field))
        for field in recipe_queries.RECIPE_FIELDS
    )

    if settings_changing:
        recipe_validation.validate_recipe_data(data)
        if not recipe_queries.recipe_is_editable(recipe_id=recipe.pk):
            image_count = models.Image.objects.filter(fujifilm_recipe_id=recipe.pk).count()
            raise RecipeCannotBeEditedError(
                recipe_id=recipe.pk,
                image_count=image_count,
                name=recipe.name,
            )
        name = data.name if data.name else recipe.name
        try:
            with transaction.atomic():
                recipe.update_settings(
                    film_simulation=data.film_simulation,
                    dynamic_range=data.dynamic_range or "",
                    d_range_priority=data.d_range_priority,
                    grain_roughness=data.grain_roughness,
                    grain_size=data.grain_size if data.grain_size is not None else "Off",
                    color_chrome_effect=data.color_chrome_effect,
                    color_chrome_fx_blue=data.color_chrome_fx_blue,
                    white_balance=data.white_balance,
                    white_balance_red=data.white_balance_red,
                    white_balance_blue=data.white_balance_blue,
                    highlight=_parse_numeric(s=data.highlight),
                    shadow=_parse_numeric(s=data.shadow),
                    color=_parse_numeric(s=data.color),
                    sharpness=_parse_numeric(s=data.sharpness),
                    high_iso_nr=_parse_numeric(s=data.high_iso_nr),
                    clarity=_parse_numeric(s=data.clarity),
                    monochromatic_color_warm_cool=_parse_numeric(s=data.monochromatic_color_warm_cool),
                    monochromatic_color_magenta_green=_parse_numeric(s=data.monochromatic_color_magenta_green),
                    name=name,
                )
        except IntegrityError:
            raise RecipeSettingsConflictError(recipe_id=recipe.pk)
    else:
        name = data.name if data.name else recipe.name
        if name != recipe.name:
            recipe.set_name(name=name)

    events.publish_event(
        event_type=events.RECIPE_UPDATED,
        recipe_id=recipe.pk,
        film_simulation=recipe.film_simulation,
    )


def remove_recipe(*, recipe_id: int, remove_recipe_card_file: bool) -> None:
    """
    Delete a FujifilmRecipe and all its associated RecipeCards.

    Removes each RecipeCard explicitly via remove_recipe_card before deleting
    the recipe, then publishes a recipe.removed event. If remove_recipe_card_file
    is True, the JPEG file for each card is also removed from the filesystem.

    :raises RecipeNotFoundError: If no recipe with *recipe_id* exists.
    :raises RecipeHasImagesError: If the recipe has one or more Images associated to it.
    """
    try:
        recipe = models.FujifilmRecipe.objects.get(pk=recipe_id)
    except models.FujifilmRecipe.DoesNotExist:
        raise RecipeNotFoundError(recipe_id=recipe_id)

    image_count = models.Image.objects.filter(fujifilm_recipe_id=recipe_id).count()
    if image_count > 0:
        raise RecipeHasImagesError(recipe_id=recipe_id, image_count=image_count, name=recipe.name)

    for card in models.RecipeCard.objects.filter(recipe_id=recipe_id):
        card_operations.remove_recipe_card(card_id=card.pk, remove_file=remove_recipe_card_file)

    recipe_name = recipe.name
    recipe.delete()

    events.publish_event(
        event_type=events.RECIPE_REMOVED,
        recipe_id=recipe_id,
        recipe_name=recipe_name,
    )
