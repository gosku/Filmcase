from django.core.management.base import BaseCommand

from src.application.usecases.images import favorite_images
from src.domain.images import operations, queries


class Command(BaseCommand):
    help = "Mark images in the given folder as favorites in the database."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to the folder containing favorite images.")

    def handle(self, *args, **options):
        folder = options["folder"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        paths = queries.collect_image_paths(folder=folder)
        self.stdout.write(f"Found {len(paths)} images.")

        marked = 0
        not_found = 0

        for path in paths:
            filename = path.split("/")[-1]
            try:
                favorite_images.mark_image_as_favorite(image_path=path)
                self.stdout.write(f"Marked as favorite: {filename}")
                marked += 1
            except operations.NoFilmSimulationError:
                self.stderr.write(f"Skipped {filename}: no Fujifilm metadata.")
                not_found += 1

        self.stdout.write(self.style.SUCCESS(f"Done. {marked} marked as favorite, {not_found} not found."))
