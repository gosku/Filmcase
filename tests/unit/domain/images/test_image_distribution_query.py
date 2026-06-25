from unittest.mock import patch

from src.domain.images.queries import Duration, get_number_images_aggregated_by


class TestGetNumberImagesAggregatedBy:
    def test_returns_empty_tuple_without_touching_orm_when_recipe_ids_empty(self):
        with patch("src.domain.images.queries.models.Image.objects") as mock_objects:
            result = get_number_images_aggregated_by(duration=Duration.MONTH, recipe_ids=[])

        assert result == ()
        mock_objects.filter.assert_not_called()
