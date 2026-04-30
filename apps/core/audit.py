from datetime import date, datetime

from .models import UnifiedAuditLog


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return value


def record_unified_audit(
    *,
    domain,
    action,
    object_type,
    actor=None,
    object_id='',
    object_name='',
    module='',
    source_id=None,
    project_id=None,
    project_name='',
    summary='',
    metadata=None,
):
    return UnifiedAuditLog.objects.create(
        domain=domain,
        action=action,
        object_type=object_type,
        object_id=str(object_id or ''),
        object_name=object_name or '',
        module=module or '',
        source_id=source_id,
        project_id=project_id,
        project_name=project_name or '',
        summary=summary or '',
        actor=actor if getattr(actor, 'is_authenticated', False) else None,
        metadata=_json_safe(metadata or {}),
    )
