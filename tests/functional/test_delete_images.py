import json

import pytest

from src.data.models import Image
from tests.factories import ImageFactory


@pytest.mark.django_db
class TestDeleteImageView:
    def test_rejects_get_requests(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/delete/")
        assert response.status_code == 405

    def test_returns_404_for_nonexistent_image(self, client):
        response = client.post("/images/99999/delete/")
        assert response.status_code == 404

    def test_deletes_image_from_db(self, client):
        image = ImageFactory()
        client.post(f"/images/{image.id}/delete/")
        assert not Image.objects.filter(pk=image.id).exists()

    def test_returns_deleted_id(self, client):
        image = ImageFactory()
        response = client.post(f"/images/{image.id}/delete/")
        assert response.status_code == 200
        assert response.json() == {"deleted": image.id}

    def test_does_not_delete_other_images(self, client):
        target = ImageFactory()
        other = ImageFactory()
        client.post(f"/images/{target.id}/delete/")
        assert Image.objects.filter(pk=other.id).exists()


@pytest.mark.django_db
class TestBulkDeleteImagesView:
    def test_rejects_get_requests(self, client):
        response = client.get("/images/bulk-delete/")
        assert response.status_code == 405

    def test_returns_400_when_body_is_empty(self, client):
        response = client.post(
            "/images/bulk-delete/",
            data="{}",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_returns_400_when_ids_is_empty_list(self, client):
        response = client.post(
            "/images/bulk-delete/",
            data=json.dumps({"ids": []}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_returns_400_on_invalid_json(self, client):
        response = client.post(
            "/images/bulk-delete/",
            data="not json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_deletes_all_requested_images(self, client):
        images = ImageFactory.create_batch(3)
        ids = [img.id for img in images]
        client.post(
            "/images/bulk-delete/",
            data=json.dumps({"ids": ids}),
            content_type="application/json",
        )
        assert Image.objects.filter(pk__in=ids).count() == 0

    def test_returns_list_of_deleted_ids(self, client):
        images = ImageFactory.create_batch(3)
        ids = [img.id for img in images]
        response = client.post(
            "/images/bulk-delete/",
            data=json.dumps({"ids": ids}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert sorted(response.json()["deleted"]) == sorted(ids)

    def test_does_not_delete_images_outside_selection(self, client):
        targets = ImageFactory.create_batch(2)
        bystander = ImageFactory()
        ids = [img.id for img in targets]
        client.post(
            "/images/bulk-delete/",
            data=json.dumps({"ids": ids}),
            content_type="application/json",
        )
        assert Image.objects.filter(pk=bystander.id).exists()

    def test_silently_ignores_nonexistent_ids(self, client):
        image = ImageFactory()
        response = client.post(
            "/images/bulk-delete/",
            data=json.dumps({"ids": [image.id, 99999]}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert image.id in response.json()["deleted"]
        assert not Image.objects.filter(pk=image.id).exists()
