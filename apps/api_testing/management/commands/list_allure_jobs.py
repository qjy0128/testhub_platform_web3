"""列出最近 N 条 Allure 报告生成任务的状态。

用法::

    python manage.py list_allure_jobs                # 默认最近 20 条
    python manage.py list_allure_jobs --limit 50
    python manage.py list_allure_jobs --status FAILED
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.api_testing.models import TestExecution


class Command(BaseCommand):
    help = '列出 Allure 报告生成任务（按 created_at 倒序）'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument(
            '--status',
            choices=[c[0] for c in TestExecution.REPORT_STATUS_CHOICES],
            help='仅显示指定 report_status 的记录',
        )

    def handle(self, *args, **options):
        qs = TestExecution.objects.select_related('test_suite').order_by('-created_at')
        if options['status']:
            qs = qs.filter(report_status=options['status'])
        qs = qs[: options['limit']]

        self.stdout.write(
            '{:<6} {:<11} {:<19} {:<10}  {}'.format(
                'ID', 'STATUS', 'GENERATED AT', 'EXEC', 'SUITE'
            )
        )
        self.stdout.write('-' * 78)
        for ex in qs:
            generated = ex.report_generated_at.strftime('%Y-%m-%d %H:%M:%S') if ex.report_generated_at else '-'
            self.stdout.write(
                '{:<6} {:<11} {:<19} {:<10}  {}'.format(
                    ex.pk,
                    ex.report_status,
                    generated,
                    ex.status,
                    ex.test_suite.name,
                )
            )
            if ex.report_status == 'FAILED' and ex.report_error:
                err = ex.report_error.strip().splitlines()[0]
                self.stdout.write(f'        ERR: {err[:120]}')
