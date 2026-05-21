from typing import Any

from django.core.management.base import BaseCommand

from src.application.usecases.images import deduplicate_images


class Command(BaseCommand):
    help = (
        "Backfill content hashes for images imported before hashing existed "
        "and merge duplicate records. Safe to run repeatedly."
    )

    def handle(self, *args: object, **options: Any) -> None:
        self.stdout.write("Deduplicating images…")

        summary = deduplicate_images.deduplicate_images()

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Hashed {summary.hashed} image(s), "
                f"merged {summary.merged} duplicate(s), "
                f"skipped {summary.files_skipped} missing file(s)."
            )
        )
