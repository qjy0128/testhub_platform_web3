import ipaddress
import socket
from urllib.parse import urlparse

from django.conf import settings


def host_resolves_to_disallowed_address(hostname):
    try:
        resolved_addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False

    for item in resolved_addresses:
        try:
            ip = ipaddress.ip_address(item[4][0])
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return True
    return False


def validate_outbound_http_url(api_url, label='URL'):
    parsed = urlparse(str(api_url or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError(f'{label} must be an absolute http(s) URL')

    if not settings.DEBUG and host_resolves_to_disallowed_address(parsed.hostname):
        raise ValueError(
            f'{label} cannot target private, loopback, reserved, multicast, '
            'or non-routable addresses in production'
        )

    return str(api_url).strip()
