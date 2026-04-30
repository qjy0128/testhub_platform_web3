import hashlib
from datetime import date, datetime
from typing import Iterable, Mapping

from django.db.models import F
from django.utils import timezone

from .models import UnifiedNotificationConfig, UnifiedNotificationTemplate, UnifiedSchedulerAlert
from .notifications import send_unified_notification


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def build_scheduler_alert_key(alert: Mapping) -> str:
    alert_type = str(alert.get('type') or alert.get('alert_type') or 'unknown').strip().lower()
    run_id = alert.get('run_id')
    job_key = str(alert.get('job_key') or '').strip()
    if run_id:
        identity = f'run:{run_id}'
    elif job_key:
        identity = f'job:{job_key}'
    else:
        seed = f"{alert_type}:{alert.get('message') or ''}:{alert.get('module') or ''}"
        digest = hashlib.sha1(seed.encode('utf-8')).hexdigest()[:16]
        identity = f'payload:{digest}'
    return f'{alert_type}:{identity}'


def _normalize_scheduler_alert_row(alert: Mapping):
    details = _json_safe(dict(alert))
    return {
        'alert_type': str(alert.get('type') or 'unknown'),
        'severity': str(alert.get('severity') or UnifiedSchedulerAlert.SEVERITY_WARNING),
        'module': str(alert.get('module') or ''),
        'source_id': alert.get('source_id') or None,
        'job_key': str(alert.get('job_key') or ''),
        'job_name': str(alert.get('job_name') or ''),
        'project_id': alert.get('project_id') or None,
        'project_name': str(alert.get('project_name') or ''),
        'message': str(alert.get('message') or ''),
        'details': details,
    }


def sync_scheduler_alerts(alerts: Iterable[Mapping], *, resolve_absent=False):
    now = timezone.now()
    normalized_rows = []
    for alert in alerts:
        row = _normalize_scheduler_alert_row(alert)
        row['alert_key'] = build_scheduler_alert_key(row)
        normalized_rows.append(row)

    keys = [row['alert_key'] for row in normalized_rows]
    existing_map = {
        item.alert_key: item
        for item in UnifiedSchedulerAlert.objects.filter(alert_key__in=keys)
    }

    created_ids = []
    touched_ids = []
    for row in normalized_rows:
        alert_key = row['alert_key']
        existing = existing_map.get(alert_key)
        if existing is None:
            created = UnifiedSchedulerAlert.objects.create(
                alert_key=alert_key,
                alert_type=row['alert_type'],
                severity=row['severity'],
                status=UnifiedSchedulerAlert.STATUS_OPEN,
                module=row['module'],
                source_id=row['source_id'],
                job_key=row['job_key'],
                job_name=row['job_name'],
                project_id=row['project_id'],
                project_name=row['project_name'],
                message=row['message'],
                details=row['details'],
                first_seen_at=now,
                last_seen_at=now,
            )
            created_ids.append(created.id)
            touched_ids.append(created.id)
            continue

        existing.alert_type = row['alert_type']
        existing.severity = row['severity']
        existing.module = row['module']
        existing.source_id = row['source_id']
        existing.job_key = row['job_key']
        existing.job_name = row['job_name']
        existing.project_id = row['project_id']
        existing.project_name = row['project_name']
        existing.message = row['message']
        existing.details = row['details']
        existing.status = UnifiedSchedulerAlert.STATUS_OPEN
        existing.acknowledged_by = None
        existing.acknowledged_at = None
        existing.resolved_at = None
        existing.last_seen_at = now
        existing.save(update_fields=[
            'alert_type',
            'severity',
            'module',
            'source_id',
            'job_key',
            'job_name',
            'project_id',
            'project_name',
            'message',
            'details',
            'status',
            'acknowledged_by',
            'acknowledged_at',
            'resolved_at',
            'last_seen_at',
        ])
        UnifiedSchedulerAlert.objects.filter(pk=existing.pk).update(occurrences=F('occurrences') + 1)
        touched_ids.append(existing.id)

    resolved_count = 0
    if resolve_absent:
        resolve_query = UnifiedSchedulerAlert.objects.filter(
            status__in=[
                UnifiedSchedulerAlert.STATUS_OPEN,
                UnifiedSchedulerAlert.STATUS_ACKNOWLEDGED,
            ]
        )
        if keys:
            resolve_query = resolve_query.exclude(alert_key__in=keys)
        resolved_count = resolve_query.update(
            status=UnifiedSchedulerAlert.STATUS_RESOLVED,
            resolved_at=now,
            acknowledged_by=None,
            acknowledged_at=None,
        )

    return {
        'created': len(created_ids),
        'active': len(touched_ids),
        'resolved': resolved_count,
    }


def _build_notification_text(alerts):
    lines = [
        f'[TestHub Scheduler] Active alerts: {len(alerts)}',
    ]
    for index, alert in enumerate(alerts[:10], start=1):
        lines.append(
            f"{index}. [{alert.severity}] {alert.alert_type} {alert.job_key or '-'} - {alert.message or '-'}"
        )
    if len(alerts) > 10:
        lines.append(f'... and {len(alerts) - 10} more alerts')
    return '\n'.join(lines)


def _get_scheduler_alert_template(actor=None):
    template, _ = UnifiedNotificationTemplate.objects.get_or_create(
        event_type=UnifiedNotificationTemplate.EVENT_SCHEDULER_ALERT,
        channel=UnifiedNotificationTemplate.CHANNEL_WEBHOOK,
        is_default=True,
        defaults={
            'name': 'Default scheduler alert',
            'subject_template': 'TestHub scheduler alerts: {{ alert_count }}',
            'body_template': '{{ alert_text }}',
            'content_type': UnifiedNotificationTemplate.CONTENT_MARKDOWN,
            'created_by': actor,
        },
    )
    return template


def notify_scheduler_alerts(alerts, *, actor=None):
    alert_items = list(alerts)
    if not alert_items:
        return {'sent': 0, 'failed': 0, 'bots': 0}

    configs = [
        config for config in UnifiedNotificationConfig.objects.filter(is_active=True)
        if any(bot.get('enabled', True) and bot.get('webhook_url') for bot in config.get_webhook_bots())
    ]
    if not configs:
        return {'sent': 0, 'failed': 0, 'bots': 0}

    text = _build_notification_text(alert_items)
    template = _get_scheduler_alert_template(actor=actor)
    sent = 0
    failed = 0
    now = timezone.now()

    for config in configs:
        logs = send_unified_notification(
            config=config,
            template=template,
            variables={
                'alert_count': len(alert_items),
                'alert_text': text,
            },
            channel=UnifiedNotificationTemplate.CHANNEL_WEBHOOK,
            created_by=actor,
        )
        if not logs:
            failed += 1
            continue
        for log in logs:
            if log.status == 'success':
                sent += 1
            else:
                failed += 1

    if sent:
        UnifiedSchedulerAlert.objects.filter(
            id__in=[alert.id for alert in alert_items],
        ).update(
            last_notified_at=now,
            notify_count=F('notify_count') + 1,
        )

    return {
        'sent': sent,
        'failed': failed,
        'bots': len(configs),
    }
