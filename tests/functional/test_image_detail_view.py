import pytest
from bs4 import BeautifulSoup

from tests.factories import FujifilmExifFactory, FujifilmRecipeFactory, ImageFactory


@pytest.mark.django_db
class TestImageDetailView:
    def test_returns_200_for_existing_image(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        assert response.status_code == 200

    def test_returns_404_for_missing_image(self, client):
        response = client.get("/images/99999/")
        assert response.status_code == 404

    def test_shows_image_element_with_image_file_url(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        img = soup.find("img", class_="detail-image")
        assert img is not None
        assert f"/images/file/{image.id}/" in img["src"]

    def test_shows_close_button_linking_to_gallery(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        close_btn = soup.find(class_="detail-close")
        assert close_btn is not None
        assert close_btn["href"] == "/images/"

    def test_close_button_is_in_top_right(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        # Close button must exist inside the detail panel header
        header = soup.find(class_="detail-header")
        assert header is not None
        assert header.find(class_="detail-close") is not None

    def test_shows_filename_in_key_info_section(self, client):
        image = ImageFactory(filename="holiday.jpg")
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        key_info = soup.find(class_="detail-key-info")
        assert key_info is not None
        assert "holiday.jpg" in key_info.get_text()

    def test_shows_iso_in_key_info_section(self, client):
        image = ImageFactory(iso="3200")
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        key_info = soup.find(class_="detail-key-info")
        assert "3200" in key_info.get_text()

    def test_shows_exposure_compensation_in_exif_section(self, client):
        exif = FujifilmExifFactory()
        image = ImageFactory(exposure_compensation="+1/3 EV", fujifilm_exif=exif)
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        exif_section = soup.find(class_="detail-exif")
        assert exif_section is not None
        assert "+1/3 EV" in exif_section.get_text()

    def test_shows_camera_info_in_key_info_section(self, client):
        image = ImageFactory(camera_make="FUJIFILM", camera_model="X-T5")
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        key_info = soup.find(class_="detail-key-info")
        assert "FUJIFILM" in key_info.get_text()
        assert "X-T5" in key_info.get_text()

    def test_shows_recipe_section_when_recipe_exists(self, client):
        recipe = FujifilmRecipeFactory(name="My Recipe", film_simulation="Classic Chrome")
        image = ImageFactory(fujifilm_recipe=recipe)
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        recipe_section = soup.find(class_="detail-recipe")
        assert recipe_section is not None
        assert "Classic Chrome" in recipe_section.get_text()

    def test_recipe_section_shows_all_recipe_fields(self, client):
        recipe = FujifilmRecipeFactory(
            name="My Recipe",
            grain_roughness="Strong",
            grain_size="Large",
            color_chrome_effect="Strong",
            color_chrome_fx_blue="Weak",
        )
        image = ImageFactory(fujifilm_recipe=recipe)
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        recipe_section = soup.find(class_="detail-recipe")
        text = recipe_section.get_text()
        assert "Strong" in text
        assert "Large" in text

    def test_hides_recipe_section_when_no_recipe(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="detail-recipe") is None

    def test_shows_exif_section_when_exif_exists(self, client):
        exif = FujifilmExifFactory(film_simulation="Velvia", af_mode="Single Point")
        image = ImageFactory(fujifilm_exif=exif)
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        exif_section = soup.find(class_="detail-exif")
        assert exif_section is not None
        assert "Single Point" in exif_section.get_text()

    def test_hides_exif_section_when_no_exif(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="detail-exif") is None

    def test_layout_has_two_columns(self, client):
        image = ImageFactory()
        response = client.get(f"/images/{image.id}/")
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="detail-image-col") is not None
        assert soup.find(class_="detail-info-col") is not None


@pytest.mark.django_db
class TestGalleryThumbnailsLinkToDetail:
    def test_gallery_thumbnails_link_to_detail_view(self, client):
        image = ImageFactory()
        response = client.get("/images/results/")
        soup = BeautifulSoup(response.content, "html.parser")
        card = soup.find(class_="image-card")
        assert card is not None
        link = card.find("a", class_="detail-link")
        assert link is not None
        assert f"/images/{image.id}/" in link["href"]

    def test_gallery_thumbnail_img_is_inside_detail_link(self, client):
        ImageFactory()
        response = client.get("/images/results/")
        soup = BeautifulSoup(response.content, "html.parser")
        link = soup.find("a", class_="detail-link")
        assert link is not None
        assert link.find("img", class_="image-thumbnail") is not None


@pytest.mark.django_db
class TestImageDetailRecipeNamePrompt:
    def _get_partial(self, client, image_id):
        return client.get(f"/images/{image_id}/", HTTP_HX_REQUEST="true")

    def test_shows_name_this_recipe_button_when_recipe_has_no_name(self, client):
        recipe = FujifilmRecipeFactory(name="")
        image = ImageFactory(fujifilm_recipe=recipe)
        response = self._get_partial(client, image.id)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="name-recipe-btn") is not None

    def test_hides_name_this_recipe_button_when_recipe_has_name(self, client):
        recipe = FujifilmRecipeFactory(name="My Recipe")
        image = ImageFactory(fujifilm_recipe=recipe)
        response = self._get_partial(client, image.id)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="name-recipe-btn") is None

    def test_name_form_posts_to_set_recipe_name_url(self, client):
        recipe = FujifilmRecipeFactory(name="")
        image = ImageFactory(fujifilm_recipe=recipe)
        response = self._get_partial(client, image.id)
        soup = BeautifulSoup(response.content, "html.parser")
        form = soup.find(id=f"recipe-name-prompt-{recipe.id}")
        assert form is not None
        assert form["hx-post"] == f"/recipes/{recipe.id}/set-name/"

    def test_no_name_prompt_when_no_recipe(self, client):
        image = ImageFactory(fujifilm_recipe=None)
        response = self._get_partial(client, image.id)
        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="name-recipe-btn") is None


@pytest.mark.django_db
class TestImageDetailPartialSendToCamera:
    def _get_partial(self, client, image_id):
        return client.get(f"/images/{image_id}/", HTTP_HX_REQUEST="true")

    def test_send_to_camera_button_present_when_recipe_has_name(self, client):
        recipe = FujifilmRecipeFactory(name="Cuban Negative")
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="send-to-camera-btn")
        assert btn is not None

    def test_send_to_camera_button_points_to_select_slot_url(self, client):
        recipe = FujifilmRecipeFactory(name="Cuban Negative")
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        btn = soup.find(class_="send-to-camera-btn")
        assert btn["hx-get"] == f"/recipes/{recipe.id}/push/"

    def test_send_to_camera_button_absent_when_recipe_has_no_name(self, client):
        recipe = FujifilmRecipeFactory(name="")
        image = ImageFactory(fujifilm_recipe=recipe)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="send-to-camera-btn") is None

    def test_send_to_camera_button_absent_when_no_recipe(self, client):
        image = ImageFactory(fujifilm_recipe=None)

        response = self._get_partial(client, image.id)

        soup = BeautifulSoup(response.content, "html.parser")
        assert soup.find(class_="send-to-camera-btn") is None
