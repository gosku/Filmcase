from django.core.management.base import BaseCommand

from src.application.usecases.images import generate_thumbnails

THUMBNAIL_WIDTH = 600


class Command(BaseCommand):
    help = "Pre-generate thumbnail cache for all images."

    def handle(self, *args, **options):
        self.stdout.write(f"Generating thumbnails at width={THUMBNAIL_WIDTH}px…")

        result = generate_thumbnails.generate_thumbnails_for_all_images(width=THUMBNAIL_WIDTH)

        for path in result.missing_paths:
            self.stderr.write(f"  Missing file: {path}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. enqueued={result.enqueued}"
                f" already_cached={result.already_cached}"
                f" missing={len(result.missing_paths)}"
            )
        )
