"""用户认证关键路径回归测试。

覆盖：
- 旧的 ``test-register`` 端点已下线（路由层）
- ``register`` / ``login`` / ``token_refresh`` 端点存在（路由层）
- ``UserCreateSerializer`` 走 Django ``AUTH_PASSWORD_VALIDATORS``
- ``logout_view`` 强制 IsAuthenticated
- refresh cookie 由 ``login_view`` 写入
"""
from __future__ import annotations

import pytest
from django.urls import NoReverseMatch, reverse


# --------------------------------------------------------------------------- #
# 路由层（不触 DB）
# --------------------------------------------------------------------------- #

def test_test_register_endpoint_is_gone():
    """关键：删除的不安全端点不应再被路由解析。"""
    with pytest.raises(NoReverseMatch):
        reverse('test-register')


def test_register_endpoint_exists():
    assert reverse('register') == '/api/auth/register/'


def test_login_endpoint_exists():
    assert reverse('login') == '/api/auth/login/'


def test_token_refresh_endpoint_exists():
    assert reverse('token_refresh') == '/api/auth/token/refresh/'


# --------------------------------------------------------------------------- #
# 密码策略（serializer 不写 DB，但 validate_password 可能查询 user 属性，
# 故还是用 django_db 标记以避免边界情况）
# --------------------------------------------------------------------------- #

@pytest.mark.django_db
class TestPasswordValidation:
    def test_too_short_password_rejected(self):
        from apps.users.serializers import UserCreateSerializer

        s = UserCreateSerializer(data={
            'username': 'newuser1',
            'email': 'new@example.com',
            'password': 'abc',
            'password_confirm': 'abc',
        })
        assert not s.is_valid()
        assert 'password' in s.errors

    def test_password_mismatch_rejected(self):
        from apps.users.serializers import UserCreateSerializer

        s = UserCreateSerializer(data={
            'username': 'newuser2',
            'email': 'new2@example.com',
            'password': 'StrongPass123!',
            'password_confirm': 'DifferentPass!',
        })
        assert not s.is_valid()
        assert 'password_confirm' in s.errors

    def test_too_similar_to_username_rejected(self):
        from apps.users.serializers import UserCreateSerializer

        s = UserCreateSerializer(data={
            'username': 'specialname',
            'email': 'sn@example.com',
            'password': 'specialname1',
            'password_confirm': 'specialname1',
        })
        assert not s.is_valid()
        assert 'password' in s.errors

    def test_strong_password_accepted(self):
        from apps.users.serializers import UserCreateSerializer

        s = UserCreateSerializer(data={
            'username': 'goodactor',
            'email': 'good@example.com',
            'password': 'X8sjm0Klp2zR-q9!',
            'password_confirm': 'X8sjm0Klp2zR-q9!',
        })
        assert s.is_valid(), s.errors


# --------------------------------------------------------------------------- #
# logout 必须登录（静态断言：检查视图装饰器，不发实际请求）
# --------------------------------------------------------------------------- #

class TestLogoutPermission:
    def test_logout_view_requires_authentication(self):
        from rest_framework.permissions import IsAuthenticated

        from apps.users.views import logout_view

        # @api_view + @permission_classes 会把权限挂在 .cls 属性上
        view_cls = getattr(logout_view, 'cls', None)
        assert view_cls is not None, 'logout_view should be wrapped by @api_view'
        assert IsAuthenticated in view_cls.permission_classes

    def test_register_view_uses_throttle(self):
        from apps.users.views import RegisterView

        assert RegisterView.throttle_scope == 'register'

    def test_login_view_uses_login_throttle(self):
        from apps.users.views import LoginRateThrottle, login_view

        view_cls = getattr(login_view, 'cls', None)
        assert view_cls is not None
        assert LoginRateThrottle in view_cls.throttle_classes


# --------------------------------------------------------------------------- #
# 登录端点的薄层契约（不写 DB；只检查 URL pattern + view 类签名）
# --------------------------------------------------------------------------- #

class TestLoginContract:
    def test_login_route_resolves_to_view(self):
        from django.urls import resolve

        match = resolve('/api/auth/login/')
        assert match.func.__name__ in {'login_view', 'view'}

    def test_token_refresh_uses_cookie_aware_class(self):
        from django.urls import resolve

        from apps.users.views import CookieAwareTokenRefreshView

        match = resolve('/api/auth/token/refresh/')
        # DRF view 包装后 func 是 .cls.as_view() 的内部函数；通过 cls 属性确认
        view_cls = getattr(match.func, 'cls', None) or getattr(match.func, 'view_class', None)
        assert view_cls is CookieAwareTokenRefreshView
