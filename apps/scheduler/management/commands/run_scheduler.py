from django.core.management.base import BaseCommand

from apps.core.scheduler_engine import DEFAULT_MAX_ATTEMPTS
from apps.scheduler.services import dispatch_due_scheduled_jobs


class Command(BaseCommand):
    help = 'Run the independent TestHub scheduler dispatcher once.'

    def add_arguments(self, parser):
        parser.add_argument('--module', action='append', dest='modules', help='Limit dispatch to one or more module keys.')
        parser.add_argument('--limit', type=int, default=None, help='Maximum due jobs to inspect.')
        parser.add_argument('--max-attempts', type=int, default=DEFAULT_MAX_ATTEMPTS, help='Retry attempts per job.')
        parser.add_argument('--dry-run', action='store_true', help='Inspect due jobs without executing them.')
        parser.add_argument('--sync', action='store_true', help='Run synchronously even when an async backend is enabled.')

    def handle(self, *args, **options):
        result = dispatch_due_scheduled_jobs(
            modules=options.get('modules'),
            limit=options.get('limit'),
            max_attempts=options.get('max_attempts'),
            dry_run=options.get('dry_run'),
            async_queue=not options.get('sync'),
        )
        self.stdout.write(self.style.SUCCESS(str(result)))
