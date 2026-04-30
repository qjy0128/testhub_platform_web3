import time

from django.conf import settings
from django.urls import resolve

from .models import RequestPerformanceMetric


class RequestPerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = bool(getattr(settings, 'REQUEST_PERFORMANCE_MONITORING_ENABLED', True))
        self.slow_threshold_ms = float(getattr(settings, 'REQUEST_PERFORMANCE_SLOW_THRESHOLD_MS', 1000))
        self.excluded_prefixes = tuple(getattr(
            settings,
            'REQUEST_PERFORMANCE_EXCLUDED_PREFIXES',
            ('/static/', '/media/', '/favicon.ico'),
        ))

    def __call__(self, request):
        if not self.enabled or self._is_excluded(request.path):
            return self.get_response(request)

        started_at = time.perf_counter()
        response = self.get_response(request)
        duration_ms = (time.perf_counter() - started_at) * 1000
        self._record_metric(request, response, duration_ms)
        response['X-TestHub-Response-Time-Ms'] = f'{duration_ms:.2f}'
        return response

    def _is_excluded(self, path):
        return any(str(path).startswith(prefix) for prefix in self.excluded_prefixes)

    def _route_name(self, request):
        try:
            match = resolve(request.path_info)
        except Exception:
            return ''
        return match.view_name or ''

    def _remote_addr(self, request):
        forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR') or None

    def _content_length(self, response):
        value = response.get('Content-Length')
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                return 0
        content = getattr(response, 'content', None)
        return len(content) if content is not None else 0

    def _record_metric(self, request, response, duration_ms):
        user = getattr(request, 'user', None)
        if not getattr(user, 'is_authenticated', False):
            user = None
        status_code = int(getattr(response, 'status_code', 0) or 0)
        try:
            RequestPerformanceMetric.objects.create(
                method=request.method,
                path=request.path[:500],
                route_name=self._route_name(request),
                query_string=request.META.get('QUERY_STRING', ''),
                status_code=status_code,
                response_time_ms=duration_ms,
                request_size=int(request.META.get('CONTENT_LENGTH') or 0),
                response_size=self._content_length(response),
                is_slow=duration_ms >= self.slow_threshold_ms,
                is_error=status_code >= 400,
                remote_addr=self._remote_addr(request),
                user=user,
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:500],
                metadata={
                    'content_type': response.get('Content-Type', ''),
                },
            )
        except Exception:
            # Observability must never break product traffic.
            return
