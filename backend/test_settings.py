"""测试专用 settings：从 backend.settings 派生 + DB 切到 SQLite 内存库。"""
from __future__ import annotations

import os

# 走默认配置入口；不依赖 .env 中的真实 MySQL 凭据。
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECRET_KEY', 'pytest-secret-not-for-prod-use-only-pytest')
os.environ.setdefault('JWT_SIGNING_KEY', 'pytest-jwt-signing-key-not-for-prod-only-pytest')
os.environ.setdefault('ALLOWED_HOSTS', 'localhost,127.0.0.1,[::1]')
os.environ.setdefault('CORS_ALLOWED_ORIGINS', 'http://localhost:3000')

from .settings import *  # noqa: F401,F403,E402

# 测试用 SQLite 内存库；不依赖 MySQL 服务。
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
        'TEST': {'NAME': ':memory:'},
    }
}

# 测试不需要 Redis broker
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = 'memory://'
CELERY_RESULT_BACKEND = 'cache+memory://'

# 测试不需要 Channels Redis
CHANNEL_LAYERS = {
    'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'},
}

# 缓存改为本机内存
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',  # 测试加速：用最快的 hasher
]

# 修复 DRF api_settings 缓存与 Django settings 不同步：
# `from .settings import *` 后又有 override，期间会触发 setting_changed signal，
# DRF 重置 user_settings 缓存。重新发一次保证 DRF 在第一次实测访问前能拿到完整字典。
def _resync_drf_settings():
    try:
        from rest_framework.settings import api_settings as _drf
        _drf.reload()  # 清缓存
    except Exception:
        pass


_resync_drf_settings()
