from typing import Literal

import attrs


@attrs.frozen
class CardTemplate:
    label_style: Literal["long", "short"]
    background_effect: Literal["none", "blur"]
    output_size: tuple[int, int]
    template_name: str


LONG_LABEL: CardTemplate = CardTemplate(
    label_style="long",
    background_effect="blur",
    output_size=(1080, 1080),
    template_name="long_label",
)
SHORT_LABEL: CardTemplate = CardTemplate(
    label_style="short",
    background_effect="blur",
    output_size=(1080, 1080),
    template_name="short_label",
)
LONG_LABEL_SHARP: CardTemplate = CardTemplate(
    label_style="long",
    background_effect="none",
    output_size=(1080, 1080),
    template_name="long_label_sharp",
)
SHORT_LABEL_SHARP: CardTemplate = CardTemplate(
    label_style="short",
    background_effect="none",
    output_size=(1080, 1080),
    template_name="short_label_sharp",
)

TEMPLATES: dict[str, CardTemplate] = {
    "long_label": LONG_LABEL,
    "short_label": SHORT_LABEL,
    "long_label_sharp": LONG_LABEL_SHARP,
    "short_label_sharp": SHORT_LABEL_SHARP,
}
