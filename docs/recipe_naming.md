# Recipe Naming

## What is a recipe?

A Fujifilm camera embeds its active shooting settings — film simulation, dynamic range,
grain, white balance, tonal adjustments, and so on — into the EXIF metadata of every JPEG
it writes. When an image is imported into this application, those fields are extracted and
stored in a `FujifilmRecipe` database row.

Recipes are **deduplicated by their field values**: two images shot with identical settings
share the same `FujifilmRecipe` row. A recipe therefore represents a specific *combination*
of creative settings, not a single image. One recipe can have thousands of images linked to
it, all shot with the same creative settings at different times.

## Recipes don't have names by default

The camera itself has no concept of recipe names — it only stores the individual setting
values. When a recipe row is created during import, its `name` field is left blank. This is
by design: the same combination of settings may not mean anything meaningful until a user
decides it does.

A recipe that has not been named can still be displayed, filtered, and even sent to a
camera. The name is optional in most contexts. The main features that require a name are:

- Displaying a human-readable label in the recipe filter dropdown of the gallery.
- Enabling the "Send to camera" button on the image detail panel (the camera expects a slot
  name, and the application uses the recipe name to fill it).

## Adding a name

### From the image detail panel

When viewing an image whose recipe has no name, the recipe section of the detail panel
shows a **"Name this recipe"** button. Clicking it replaces the button with a small inline
form:

```
[ Recipe name (max 25 chars) ]  [ OK ]  [ Cancel ]
```

- Typing a name and pressing **OK** (or Enter) submits the name via an HTMX POST request.
  The form is replaced in-place with the name and "Send to camera" button — no page reload.
- Pressing **Cancel** discards the form and restores the original button, also without a
  page reload.

If the name is invalid, the form stays open and an error message is shown inline. If an
unexpected server error occurs, the form also stays open with a generic error message.

All of this happens within the same detail panel using HTMX swaps, so the gallery and image
context are preserved throughout.

### Validation rules

Recipe names must satisfy two constraints, inherited from the camera's own slot naming
limits:

| Rule | Detail |
|---|---|
| Maximum length | 25 characters |
| Character set | ASCII only |

Names that violate either rule are rejected with a `RecipeNameValidationError` before
anything is written to the database.

## How it works under the hood

### Operation: `set_recipe_name`

The core logic lives in `src/domain/images/operations.py`:

```python
set_recipe_name(*, recipe: FujifilmRecipe, name: str) -> None
```

It validates the name, updates only the `name` field of the recipe row with
`save(update_fields=["name"])`, then publishes a `recipe.image.updated` event carrying the
new name and the recipe's primary key.

### View: `SetRecipeNameView`

`POST /recipes/<id>/set-name/` is handled by `SetRecipeNameView` in
`src/interfaces/views.py`. Its `dispatch` method resolves the `recipe_id` URL parameter to
a `FujifilmRecipe` object (404 if not found). The `post` method calls `set_recipe_name` and
returns one of two HTML partials:

- **Success** → `recipes/_recipe_name_row.html`: the name value and the "Send to camera"
  button, ready to be swapped into the detail panel.
- **Error** → `recipes/_recipe_name_prompt.html`: the name form with the error message
  shown and the form state visible, ready to be swapped back in for the user to correct the
  input.

### HTMX wiring in the detail panel

The `_recipe_name_prompt.html` partial is a `<form>` element with `hx-post` and
`hx-swap="outerHTML"`. When the server responds, HTMX replaces the entire form element with
whatever the view returns — either the name row on success or a fresh copy of the form
(with error) on failure. The button/form toggle is handled client-side with inline
JavaScript on the button `onclick` attributes, so no extra server round-trip is needed just
to show or hide the form.
