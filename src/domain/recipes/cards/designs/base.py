from __future__ import annotations

import abc
from typing import ClassVar

from src.data import models
from src.domain.recipes.cards import rendering


class CardDesign(abc.ABC):
    """
    A recipe card design: a self-contained strategy for composing a card image.

    Each concrete design owns its full layout in render(). Design-agnostic
    concerns (QR generation and spec, EXIF embedding, file saving) live in the
    rendering module and the cards operations module, so every design produces a
    scannable, importable card regardless of its look.

    Concrete designs declare three pieces of metadata:

    - ``template_name``: the identifier persisted on ``RecipeCard.template`` and
      emitted in the ``recipe.card.created`` event. Must stay stable across
      releases so existing rows and event history remain meaningful.
    - ``output_size``: the fixed output canvas size in pixels.
    - ``requires_background_image``: whether the design needs a real photo (a
      photo-centric layout) rather than being able to fall back to a generated
      gradient background.
    """

    output_size: ClassVar[tuple[int, int]]
    requires_background_image: ClassVar[bool]

    @property
    @abc.abstractmethod
    def template_name(self) -> str:
        """
        Return the stable identifier stored on the card and the event.
        """

    @abc.abstractmethod
    def render(
        self,
        *,
        recipe: models.FujifilmRecipe,
        background_image: models.Image | None,
    ) -> rendering.RenderedCard:
        """
        Compose the card image for *recipe* over *background_image*.

        When *background_image* is None the design falls back to a generated
        gradient background (only designs where requires_background_image is
        False are expected to be called this way).
        """
