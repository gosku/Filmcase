from django.core.management.base import BaseCommand

from src.application.usecases.images import rate_images


class Command(BaseCommand):
    help = "Rate images in the given folder with the specified rating."

    def add_arguments(self, parser):
        parser.add_argument("folder", type=str, help="Path to the folder containing images to rate.")
        parser.add_argument("--rating", type=int, required=True, help="Rating to apply to each image.")

    def handle(self, *args, **options):
        folder = options["folder"]
        rating = options["rating"]
        self.stdout.write(f"Scanning {folder} for JPG files…")

        result = rate_images.rate_images_in_folder(folder=folder, rating=rating)

        for path in result.rated:
            self.stdout.write(f"Rated {path.split('/')[-1]} with {rating}")
        for path in result.skipped:
            self.stderr.write(f"Skipped {path.split('/')[-1]}: unable to rate image.")

        self.stdout.write(self.style.SUCCESS(
            f"Done. {len(result.rated)} rated, {len(result.skipped)} skipped."
        ))
