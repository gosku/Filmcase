# Film simulations that support the monochromatic color shift controls (Warm/Cool, Magenta/Green).
MONOCHROMATIC_FILM_SIMULATIONS: frozenset[str] = frozenset({
    "Monochrome STD",
    "Monochrome Yellow",
    "Monochrome Red",
    "Monochrome Green",
    "Sepia",
    "Acros STD",
    "Acros Yellow",
    "Acros Red",
    "Acros Green",
})

# Maps film_simulation field value → logo filename under src/interfaces/static/images/.
# Keys must exactly match the string values stored in FujifilmRecipe.film_simulation,
# which are defined by FILM_SIMULATION_TO_PTP in src/data/camera/constants.py.
FILM_SIM_LOGO: dict[str, str] = {
    "Provia":               "provia.png",
    "Velvia":               "velvia.png",
    "Astia":                "astia.png",
    "Pro Neg. Hi":          "pro-neg-hi.png",
    "Pro Neg. Std":         "pro-neg-std.png",
    "Monochrome STD":       "monochrome.png",
    "Monochrome Yellow":    "monochrome-ye-filter.png",
    "Monochrome Red":       "monochrome-r-filter.png",
    "Monochrome Green":     "monochrome-g-filter.png",
    "Sepia":                "sepia.png",
    "Classic Chrome":       "classic-chrome.png",
    "Acros STD":            "acros.png",
    "Acros Yellow":         "acros-ye-filter.png",
    "Acros Red":            "acros-r-filter.png",
    "Acros Green":          "acros-g-filter.png",
    "Eterna":               "eterna.png",
    "Classic Negative":     "classic-neg.png",
    "Eterna Bleach Bypass": "eterna-bleach-bypass.png",
    "Nostalgic Negative":   "nostalgic-neg.png",
    "Reala Ace":            "reala-ace.png",
}
