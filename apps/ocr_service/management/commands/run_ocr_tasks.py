from django.core.management.base import BaseCommand

from apps.ocr_service.services import run_pending_ocr_tasks


class Command(BaseCommand):
    help = 'Run pending OCR tasks.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        result = run_pending_ocr_tasks(limit=options.get('limit'))
        self.stdout.write(self.style.SUCCESS(
            f"OCR tasks succeeded={result['succeeded']} "
            f"failed={result['failed']} pending_retry={result['pending_retry']}"
        ))
