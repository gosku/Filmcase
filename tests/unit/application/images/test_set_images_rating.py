from unittest.mock import patch

import pytest

from src.application.usecases.images import set_images_rating as uc
from src.domain.images.operations import InvalidImageRatingError

_OP = "src.application.usecases.images.set_images_rating.image_operations.set_images_rating"


class TestSetImagesRatingResult:
    def test_result_carries_rated_count_from_operation(self) -> None:
        with patch(_OP, return_value=2) as mock_op:
            result = uc.set_images_rating(image_ids=[1, 2, 3], rating=4)
        mock_op.assert_called_once_with(image_ids=[1, 2, 3], rating=4)
        assert result.rated_count == 2
        assert result.requested_count == 3
        assert result.not_found_count == 1

    def test_not_found_count_is_zero_when_all_rated(self) -> None:
        with patch(_OP, return_value=3):
            result = uc.set_images_rating(image_ids=[1, 2, 3], rating=4)
        assert result.not_found_count == 0


class TestSetImagesRatingErrorTranslation:
    def test_translates_invalid_image_rating_error(self) -> None:
        with patch(_OP, side_effect=InvalidImageRatingError(rating=6)):
            with pytest.raises(uc.InvalidRatingError) as exc_info:
                uc.set_images_rating(image_ids=[1], rating=6)
        assert exc_info.value.rating == 6
