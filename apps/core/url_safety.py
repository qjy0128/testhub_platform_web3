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


def _ssrf_enforced() -> bool:
    """SSRF 校验默认始终开启；可通过显式开关在本机调试时放行。

    为避免 dev 模式下隐式打开整张内网，需要在 .env 中显式设置
    ``ALLOW_INTERNAL_OUTBOUND_URLS=True`` 才会跳过。
    """
    if getattr(settings, 'ALLOW_INTERNAL_OUTBOUND_URLS', False):
        return False
    return True


def validate_outbound_http_url(api_url, label='URL'):
    parsed = urlparse(str(api_url or '').strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError(f'{label} must be an absolute http(s) URL')

    if _ssrf_enforced() and host_resolves_to_disallowed_address(parsed.hostname):
        raise ValueError(
            f'{label} cannot target private, loopback, reserved, multicast, '
            'or non-routable addresses'
        )

    return str(api_url).strip()
