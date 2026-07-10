import shutil
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import ChunkedUpload


class Command(BaseCommand):
    help = 'Remove expired, unconsumed upload sessions and their temporary files.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only report how many sessions would be removed.')

    def handle(self, *args, **options):
        uploads = ChunkedUpload.objects.filter(consumed_at__isnull=True, expires_at__lte=timezone.now())
        count = uploads.count()
        if options['dry_run']:
            self.stdout.write(f'{count} expired upload session(s) would be removed.')
            return

        for upload in uploads.iterator():
            shutil.rmtree(Path(settings.WORK_UPLOAD_CHUNK_DIR) / str(upload.upload_id), ignore_errors=True)
            if upload.file:
                upload.file.delete(save=False)
            upload.delete()
        self.stdout.write(self.style.SUCCESS(f'Removed {count} expired upload session(s).'))
