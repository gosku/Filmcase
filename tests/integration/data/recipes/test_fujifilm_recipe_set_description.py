import pytest

from tests.factories import FujifilmRecipeFactory


@pytest.mark.django_db
class TestFujifilmRecipeSetDescription:
    def test_writes_description_field(self):
        recipe = FujifilmRecipeFactory()

        recipe.set_description(description="Some notes about this recipe.")

        recipe.refresh_from_db()
        assert recipe.description == "Some notes about this recipe."

    def test_overwrites_previous_value(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_description(description="First version")

        recipe.set_description(description="Second version")

        recipe.refresh_from_db()
        assert recipe.description == "Second version"

    def test_accepts_empty_string(self):
        recipe = FujifilmRecipeFactory()
        recipe.set_description(description="Something to clear")

        recipe.set_description(description="")

        recipe.refresh_from_db()
        assert recipe.description == ""

    def test_accepts_very_long_text(self):
        # description is an unconstrained TextField; the mutator must store
        # whatever the caller passes verbatim.
        recipe = FujifilmRecipeFactory()
        long_text = "x" * 10_000

        recipe.set_description(description=long_text)

        recipe.refresh_from_db()
        assert recipe.description == long_text
