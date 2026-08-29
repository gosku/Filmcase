from typing import Any

from django.core.management.base import BaseCommand

from src.application.usecases.images import generate_thumbnails
from src.domain.settings import queries as settings_queries


class Command(BaseCommand):
    help = "Pre-generate thumbnail cache for all images."

    def handle(self, *args: object, **options: Any) -> None:
        for width in settings_queries.get_thumbnail_widths():
            self.stdout.write(f"Generating thumbnails at width={width}px…")

            result = generate_thumbnails.generate_thumbnails_for_all_images(width=width)

            for path in result.missing_paths:
                self.stderr.write(f"  Missing file: {path}")

            self.stdout.write(
                self.style.SUCCESS(
                    f"Done. enqueued={result.enqueued}"
                    f" already_cached={result.already_cached}"
                    f" missing={len(result.missing_paths)}"
                )
            )
