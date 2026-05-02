import logging
import os

from celery import Celery
from celery.signals import task_failure

logger = logging.getLogger(__name__)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    logger.debug('Request: %r', self.request)


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, traceback=None, einfo=None, **kwargs):
    """统一记录 Celery 任务异常。

    避免任务静默失败：每个 task 异常都会留下一条 ERROR 级别日志，
    生产环境若接入 Sentry / 钉钉告警，可以在这里挂二级回调。
    """
    task_name = getattr(sender, 'name', repr(sender))
    logger.error(
        'Celery task failed: name=%s task_id=%s exception=%r',
        task_name,
        task_id,
        exception,
        exc_info=einfo.exc_info if einfo else None,
    )
