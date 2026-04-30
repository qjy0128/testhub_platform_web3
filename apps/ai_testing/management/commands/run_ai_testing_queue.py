from django.core.management.base import BaseCommand

from apps.ai_testing.services import run_pending_ai_testing_runs


class Command(BaseCommand):
    help = 'Run pending AI testing runs.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        result = run_pending_ai_testing_runs(limit=options.get('limit'))
        self.stdout.write(
            self.style.SUCCESS(
                'AI testing queue finished: '
                f"total={result['total']} "
                f"succeeded={result['succeeded']} "
                f"failed={result['failed']} "
                f"cancelled={result['cancelled']}"
            )
        )
