from django.core.management.base import BaseCommand

from apps.knowledge_base.services import index_pending_documents


class Command(BaseCommand):
    help = 'Index pending or failed knowledge documents.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        result = index_pending_documents(limit=options.get('limit'))
        self.stdout.write(self.style.SUCCESS(
            f"Knowledge documents indexed={result['indexed']} failed={result['failed']}"
        ))
