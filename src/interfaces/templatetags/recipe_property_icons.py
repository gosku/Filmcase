from django import template

register = template.Library()

# Recipe field name to the <symbol> id in includes/property_icon_sprite.html.
# Icons are presentation, so this mapping lives here rather than in the domain,
# which knows only the field names.
_ICON_BY_FIELD: dict[str, str] = {
    "film_simulation": "prop-film-sim",
    "dynamic_range": "prop-dynamic-range",
    "d_range_priority": "prop-dr-priority",
    "grain_roughness": "prop-grain-roughness",
    "grain_size": "prop-grain-size",
    "color_chrome_effect": "prop-color-chrome",
    "color_chrome_fx_blue": "prop-cc-fx-blue",
    "white_balance": "prop-white-balance",
    # The two fine-tune axes share the shift arrow.
    "white_balance_red": "prop-wb-shift",
    "white_balance_blue": "prop-wb-shift",
    "highlight": "prop-highlight",
    "shadow": "prop-shadow",
    "color": "prop-color",
    "sharpness": "prop-sharpness",
    "high_iso_nr": "prop-high-iso-nr",
    "clarity": "prop-clarity",
    # The design has no monochrome glyphs, so reuse the nearest ones.
    "monochromatic_color_warm_cool": "prop-color",
    "monochromatic_color_magenta_green": "prop-wb-shift",
}

_FALLBACK_ICON = "prop-grain-size"


@register.filter
def property_icon(field: str) -> str:
    """
    Return the sprite symbol id for a recipe field, for use in <use href="#...">.
    """
    return _ICON_BY_FIELD.get(field, _FALLBACK_ICON)
