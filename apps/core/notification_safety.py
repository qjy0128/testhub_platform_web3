from copy import deepcopy
from urllib.parse import urlparse, urlunparse

from apps.core.url_safety import validate_outbound_http_url


def validate_notification_webhook_url(webhook_url, *, bot_type='webhook'):
    return validate_outbound_http_url(
        webhook_url,
        label=f'{bot_type} webhook URL',
    )


def validate_notification_webhook_bots(webhook_bots):
    if not webhook_bots:
        return webhook_bots
    if not isinstance(webhook_bots, dict):
        raise ValueError('webhook_bots must be an object.')

    sanitized_bots = deepcopy(webhook_bots)
    for bot_type, bot_config in sanitized_bots.items():
        if bot_config in (None, ''):
            continue
        if not isinstance(bot_config, dict):
            raise ValueError(f'{bot_type} webhook config must be an object.')

        webhook_url = bot_config.get('webhook_url')
        if webhook_url:
            bot_config['webhook_url'] = validate_notification_webhook_url(
                webhook_url,
                bot_type=bot_type,
            )

    return sanitized_bots


def redact_webhook_url(webhook_url):
    parsed = urlparse(str(webhook_url or ''))
    if not parsed.scheme or not parsed.netloc:
        return '***'

    return urlunparse((
        parsed.scheme,
        parsed.netloc,
        '/***',
        '',
        '',
        '',
    ))
