from django.core.management.base import BaseCommand

from src.data.models import Image
from src.interfaces.tasks import process_image_task


class Command(BaseCommand):
    help = "Find images without a fujifilm_recipe and reprocess them to create one."

    def handle(self, *args, **options):
        images = Image.objects.without_recipe()
        total = images.count()
        self.stdout.write(f"Found {total} image(s) without a recipe.")

        for image in images:
            process_image_task.delay(image.filepath)

        self.stdout.write(self.style.SUCCESS(f"Enqueued {total} image(s) for reprocessing."))
