from django.core.management.base import BaseCommand

from src.domain.images import events, queries
from src.interfaces import tasks


class Command(BaseCommand):
    help = "Enqueue a Celery task for every JPG image found in the given folder."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to the folder containing images.")

    def handle(self, *args, **options):
        folder = options["folder"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        paths = queries.collect_image_paths(folder=folder)
        total = len(paths)
        self.stdout.write(f"Found {total} images. Enqueuing tasks…")

        for path in paths:
            tasks.process_image_task.apply_async(kwargs={"image_path": path})
            events.publish_event(
                event_type=events.TASK_IMAGE_ENQUEUED,
                image_path=path,
            )

        self.stdout.write(self.style.SUCCESS(f"Successfully enqueued {total} tasks."))
