import time

from django.core.management import call_command
from django.core.management.base import BaseCommand

from apps.core.scheduler_engine import DEFAULT_MAX_ATTEMPTS, run_due_scheduled_jobs


class Command(BaseCommand):
    help = 'Run the TestHub unified scheduler once or continuously.'

    def add_arguments(self, parser):
        parser.add_argument('--interval', type=int, default=60)
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--module', action='append', dest='modules', default=None)
        parser.add_argument('--max-attempts', type=int, default=DEFAULT_MAX_ATTEMPTS)
        parser.add_argument('--lock-seconds', type=int, default=1800)
        parser.add_argument('--defer-blocked-seconds', type=int, default=60)
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--skip-star-maintenance',
            action='store_true',
            help='Skip knowledge base indexing and OCR pending-task maintenance.',
        )

    def handle(self, *args, **options):
        interval = options['interval']
        while True:
            summary = run_due_scheduled_jobs(
                modules=options.get('modules'),
                limit=options.get('limit'),
                max_attempts=options.get('max_attempts'),
                lock_seconds=options.get('lock_seconds'),
                defer_blocked_seconds=options.get('defer_blocked_seconds'),
                dry_run=options.get('dry_run'),
            )
            self.stdout.write(
                self.style.SUCCESS(
                    'Unified scheduler cycle: '
                    f"due={summary['due']} "
                    f"started={summary['started']} "
                    f"succeeded={summary['succeeded']} "
                    f"failed={summary['failed']} "
                    f"skipped={summary['skipped']}"
                )
            )

            if not options.get('skip_star_maintenance') and not options.get('dry_run'):
                call_command('index_knowledge_documents', limit=options.get('limit'))
                call_command('run_ocr_tasks', limit=options.get('limit'))

            if options['once']:
                break

            self.stdout.write(f'Waiting {interval} seconds before the next scheduler cycle.')
            time.sleep(interval)
