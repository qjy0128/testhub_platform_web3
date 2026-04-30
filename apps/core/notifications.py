import base64
import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

from .notification_safety import redact_webhook_url, validate_notification_webhook_url
from .models import (
    UnifiedNotificationConfig,
    UnifiedNotificationSendLog,
    UnifiedNotificationTemplate,
)


@dataclass
class RenderedNotification:
    subject: str
    body: str
    content_type: str


def _lookup_variable(variables: dict[str, Any], key: str) -> Any:
    value: Any = variables
    for part in key.split('.'):
        if isinstance(value, dict):
            value = value.get(part, '')
        else:
            value = getattr(value, part, '')
        if value is None:
            return ''
    return value


def render_text_template(template_text: str, variables: dict[str, Any]) -> str:
    import re

    pattern = re.compile(r'{{\s*([A-Za-z0-9_.-]+)\s*}}')

    def replace(match):
        value = _lookup_variable(variables, match.group(1))
        return str(value)

    return pattern.sub(replace, template_text or '')


def render_notification_template(
    template: UnifiedNotificationTemplate,
    variables: dict[str, Any] | None = None,
) -> RenderedNotification:
    variables = variables or {}
    return RenderedNotification(
        subject=render_text_template(template.subject_template, variables),
        body=render_text_template(template.body_template, variables),
        content_type=template.content_type,
    )


def build_dingtalk_signed_url(webhook_url: str, secret: str) -> str:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f'{timestamp}\n{secret}'.encode('utf-8')
    digest = hmac.new(secret.encode('utf-8'), string_to_sign, hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest).decode('utf-8'))
    separator = '&' if '?' in webhook_url else '?'
    return f'{webhook_url}{separator}timestamp={timestamp}&sign={sign}'


def build_feishu_sign(secret: str, timestamp: int | None = None) -> dict[str, str]:
    timestamp = timestamp or int(time.time())
    string_to_sign = f'{timestamp}\n{secret}'
    digest = hmac.new(string_to_sign.encode('utf-8'), b'', hashlib.sha256).digest()
    return {
        'timestamp': str(timestamp),
        'sign': base64.b64encode(digest).decode('utf-8'),
    }


def _attachment_summary(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            'filename': item.get('filename', 'attachment'),
            'content_type': item.get('content_type', 'application/octet-stream'),
            'size': len(str(item.get('content', '') or item.get('content_base64', ''))),
        }
        for item in attachments
    ]


def _attachment_content(item: dict[str, Any]) -> bytes:
    if item.get('content_base64'):
        return base64.b64decode(item['content_base64'])
    content = item.get('content', '')
    if isinstance(content, bytes):
        return content
    return str(content).encode('utf-8')


def _first_bot(config: UnifiedNotificationConfig) -> dict[str, Any] | None:
    for bot in config.get_webhook_bots():
        if bot.get('enabled', True) and bot.get('webhook_url'):
            return bot
    return None


def build_webhook_payload(
    bot_type: str,
    rendered: RenderedNotification,
    secret: str = '',
) -> dict[str, Any]:
    text = rendered.body
    if bot_type == 'dingtalk':
        if rendered.content_type == UnifiedNotificationTemplate.CONTENT_MARKDOWN:
            return {
                'msgtype': 'markdown',
                'markdown': {
                    'title': rendered.subject or 'TestHub Notification',
                    'text': text,
                },
            }
        return {'msgtype': 'text', 'text': {'content': text}}

    if bot_type == 'feishu':
        payload = {'msg_type': 'text', 'content': {'text': text}}
        if secret:
            payload.update(build_feishu_sign(secret))
        return payload

    if bot_type in ['wechat', 'wecom']:
        if rendered.content_type == UnifiedNotificationTemplate.CONTENT_MARKDOWN:
            return {'msgtype': 'markdown', 'markdown': {'content': text}}
        return {'msgtype': 'text', 'text': {'content': text}}

    return {
        'subject': rendered.subject,
        'content': text,
        'content_type': rendered.content_type,
    }


def send_email_notification(
    config: UnifiedNotificationConfig,
    rendered: RenderedNotification,
    recipients: list[str],
    attachments: list[dict[str, Any]] | None = None,
    template: UnifiedNotificationTemplate | None = None,
    created_by=None,
) -> UnifiedNotificationSendLog:
    attachments = attachments or []
    log_data = {
        'config': config,
        'template': template,
        'channel': UnifiedNotificationSendLog.CHANNEL_EMAIL,
        'target': ','.join(recipients),
        'subject': rendered.subject,
        'content': rendered.body,
        'attachments': _attachment_summary(attachments),
        'created_by': created_by,
    }
    try:
        email = EmailMultiAlternatives(
            subject=rendered.subject or 'TestHub Notification',
            body=rendered.body,
            from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', None),
            to=recipients,
        )
        if rendered.content_type == UnifiedNotificationTemplate.CONTENT_HTML:
            email.attach_alternative(rendered.body, 'text/html')
        for item in attachments:
            email.attach(
                item.get('filename', 'attachment'),
                _attachment_content(item),
                item.get('content_type', 'application/octet-stream'),
            )
        email.send(fail_silently=False)
        return UnifiedNotificationSendLog.objects.create(
            **log_data,
            status=UnifiedNotificationSendLog.STATUS_SUCCESS,
            payload={'recipient_count': len(recipients)},
        )
    except Exception as exc:
        return UnifiedNotificationSendLog.objects.create(
            **log_data,
            status=UnifiedNotificationSendLog.STATUS_FAILED,
            error_message=str(exc),
        )


def send_webhook_notification(
    config: UnifiedNotificationConfig,
    rendered: RenderedNotification,
    bot: dict[str, Any],
    attachments: list[dict[str, Any]] | None = None,
    template: UnifiedNotificationTemplate | None = None,
    created_by=None,
    timeout: int = 10,
) -> UnifiedNotificationSendLog:
    attachments = attachments or []
    bot_type = bot.get('type') or 'generic'
    webhook_url = bot.get('webhook_url')
    secret = bot.get('secret') or ''
    payload = build_webhook_payload(bot_type, rendered, secret=secret)
    if attachments:
        payload['attachments'] = _attachment_summary(attachments)
    log_data = {
        'config': config,
        'template': template,
        'channel': UnifiedNotificationSendLog.CHANNEL_WEBHOOK,
        'target': redact_webhook_url(webhook_url),
        'subject': rendered.subject,
        'content': rendered.body,
        'attachments': _attachment_summary(attachments),
        'payload': payload,
        'created_by': created_by,
    }
    try:
        safe_webhook_url = validate_notification_webhook_url(
            webhook_url,
            bot_type=bot_type,
        )
        signed_url = (
            build_dingtalk_signed_url(safe_webhook_url, secret)
            if bot_type == 'dingtalk' and secret
            else safe_webhook_url
        )
        response = requests.post(signed_url, json=payload, timeout=timeout)
        response.raise_for_status()
        return UnifiedNotificationSendLog.objects.create(
            **log_data,
            status=UnifiedNotificationSendLog.STATUS_SUCCESS,
            response_status=response.status_code,
        )
    except Exception as exc:
        response_status = getattr(getattr(exc, 'response', None), 'status_code', None)
        return UnifiedNotificationSendLog.objects.create(
            **log_data,
            status=UnifiedNotificationSendLog.STATUS_FAILED,
            error_message=str(exc),
            response_status=response_status,
        )


def send_unified_notification(
    config: UnifiedNotificationConfig,
    template: UnifiedNotificationTemplate,
    variables: dict[str, Any] | None = None,
    channel: str | None = None,
    recipients: list[str] | None = None,
    attachments: list[dict[str, Any]] | None = None,
    created_by=None,
) -> list[UnifiedNotificationSendLog]:
    rendered = render_notification_template(template, variables)
    channel = channel or template.channel
    config_payload = config.webhook_bots or {}
    logs: list[UnifiedNotificationSendLog] = []

    if channel in [UnifiedNotificationTemplate.CHANNEL_ALL, UnifiedNotificationTemplate.CHANNEL_EMAIL]:
        email_recipients = recipients or config_payload.get('email', {}).get('recipients') or []
        if config.config_type == 'email' or email_recipients:
            logs.append(
                send_email_notification(
                    config,
                    rendered,
                    email_recipients,
                    attachments=attachments,
                    template=template,
                    created_by=created_by,
                )
            )

    if channel in [UnifiedNotificationTemplate.CHANNEL_ALL, UnifiedNotificationTemplate.CHANNEL_WEBHOOK]:
        bot = _first_bot(config)
        if bot:
            logs.append(
                send_webhook_notification(
                    config,
                    rendered,
                    bot,
                    attachments=attachments,
                    template=template,
                    created_by=created_by,
                )
            )

    return logs
