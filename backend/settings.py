# https://newpanjing.github.io/simpleui_docs/config.html#%E5%9B%BE%E6%A0%87%E8%AF%B4%E6%98%8E

from pathlib import Path
from decouple import config
from django.core.exceptions import ImproperlyConfigured
import os

BASE_DIR = Path(__file__).resolve().parent.parent

def _csv(value):
    return [item.strip() for item in value.split(',') if item.strip()]


def _dedupe(values):
    return list(dict.fromkeys(values))


DEBUG = config('DEBUG', default=False, cast=bool)

SECRET_KEY = config('SECRET_KEY', default='')
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('SECRET_KEY 必须通过环境变量配置，且不能使用 Django 示例密钥')

# JWT 签名密钥（建议与 SECRET_KEY 分开，生产环境必须独立配置）
JWT_SIGNING_KEY = config('JWT_SIGNING_KEY', default=SECRET_KEY)
if not DEBUG and JWT_SIGNING_KEY == SECRET_KEY:
    import warnings
    warnings.warn(
        '生产环境应将 JWT_SIGNING_KEY 与 SECRET_KEY 分开配置，'
        '请设置独立的 JWT_SIGNING_KEY 环境变量。',
        RuntimeWarning,
    )

APP_AUTOMATION_ALLOWED_SCRCPY_PATHS = _dedupe(
    config('APP_AUTOMATION_ALLOWED_SCRCPY_PATHS', default='scrcpy', cast=_csv)
)

# 根据DEBUG模式设置ALLOWED_HOSTS，生产环境不应使用通配符
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,[::1]',
    cast=_csv,
)
if not DEBUG and (not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS):
    raise ImproperlyConfigured('生产环境必须显式配置 ALLOWED_HOSTS，且不能使用通配符')

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

if config('ENABLE_SIMPLEUI', default=False, cast=bool):
    DJANGO_APPS.insert(0, 'simpleui')

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',  # 添加JWT支持
    'rest_framework_simplejwt.token_blacklist',  # JWT token黑名单
    'corsheaders',
    'django_filters',
    'drf_spectacular',
    'channels',
]

LOCAL_APPS = [
    'apps.users',
    'apps.projects',
    'apps.testcases',
    'apps.testsuites',
    'apps.executions',
    'apps.reports',
    'apps.reviews',
    'apps.versions',
    'apps.assistant',
    'apps.requirement_analysis',
    'apps.api_testing',
    'apps.ui_automation.apps.UiAutomationConfig',
    'apps.app_automation.apps.AppAutomationConfig',  # APP自动化测试
    'apps.core',
    'apps.scheduler.apps.SchedulerConfig',
    'apps.ai_testing.apps.AiTestingConfig',
    'apps.knowledge_base.apps.KnowledgeBaseConfig',
    'apps.ocr_service.apps.OcrServiceConfig',
    'apps.data_factory',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.core.middleware.RequestPerformanceMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'backend.wsgi.application'
ASGI_APPLICATION = 'backend.asgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': config('DB_NAME', default='testhub'),
        'USER': config('DB_USER', default='root'),
        'PASSWORD': config('DB_PASSWORD', default=''),  # 移除硬编码默认密码
        'HOST': config('DB_HOST', default='127.0.0.1'),
        'PORT': config('DB_PORT', default='3306'),
        'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {
            'charset': 'utf8mb4',
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
            'connect_timeout': config('DB_CONNECT_TIMEOUT', default=5, cast=int),
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/
# Supported language codes: 'en-us' (English), 'zh-hans' (Simplified Chinese), 'ja' (Japanese), 'ko' (Korean), etc.
# See: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones for timezone list
LANGUAGE_CODE = config('LANGUAGE_CODE', default='zh-hans')
TIME_ZONE = config('TIME_ZONE', default='Asia/Shanghai')
USE_I18N = True
USE_TZ = True

# `STATIC_*`：Django collectstatic 的产物（前端构建后的静态资源）
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_collected')

# `STATIC_FILES_*`：数据工厂等业务模块写入的运行期静态资源
# 这是与 STATIC_ROOT 不同的目录，避免 collectstatic 覆盖业务文件。
# 生产环境需要由 nginx 等反代将 /static_files/ 指向 STATIC_FILES_ROOT。
STATIC_FILES_URL = '/static_files/'
STATIC_FILES_ROOT = os.path.join(BASE_DIR, 'static_files')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 上传体积限制（默认 25MB；OCR/需求文档/知识库等场景可通过环境变量调大）
DATA_UPLOAD_MAX_MEMORY_SIZE = config('DATA_UPLOAD_MAX_MEMORY_SIZE', default=25 * 1024 * 1024, cast=int)
FILE_UPLOAD_MAX_MEMORY_SIZE = config('FILE_UPLOAD_MAX_MEMORY_SIZE', default=25 * 1024 * 1024, cast=int)
# 用于业务侧 FileField 校验：单文件上限（默认与上传上限一致）
MAX_UPLOAD_FILE_SIZE = config('MAX_UPLOAD_FILE_SIZE', default=25 * 1024 * 1024, cast=int)

# SSRF 防护：是否允许出站 HTTP 请求命中私有 / 本机 / 保留地址。
# 默认 False（即生产/开发都会拒绝），仅在确需访问内网服务时显式打开。
ALLOW_INTERNAL_OUTBOUND_URLS = config('ALLOW_INTERNAL_OUTBOUND_URLS', default=False, cast=bool)

# 字段级加密密钥（44 字节 base64 urlsafe）。
# 留空时 ``apps.core.encrypted_fields`` 会基于 SECRET_KEY 派生，方便开发；
# 生产环境必须显式独立配置，便于以后做 key rotation。
# 生成方式：python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
FIELD_ENCRYPTION_KEY = config('FIELD_ENCRYPTION_KEY', default='')

# SSE 长连接的最大保活时长（秒）。超过此值会主动断流，让前端发起新连接。
SSE_MAX_TIMEOUT_SECONDS = config('SSE_MAX_TIMEOUT_SECONDS', default=3600, cast=int)

# Refresh token cookie：登录时把 refresh token 写入 httpOnly cookie，前端不再持久化。
# 名称 / 路径 / SameSite 可通过环境变量覆盖。
JWT_REFRESH_COOKIE_NAME = config('JWT_REFRESH_COOKIE_NAME', default='th_refresh')
JWT_REFRESH_COOKIE_PATH = config('JWT_REFRESH_COOKIE_PATH', default='/api/auth/')
JWT_REFRESH_COOKIE_SAMESITE = config('JWT_REFRESH_COOKIE_SAMESITE', default='Lax')
JWT_REFRESH_COOKIE_SECURE = config('JWT_REFRESH_COOKIE_SECURE', default=not DEBUG, cast=bool)

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# DRF Settings
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'backend.authentication.ResilientJWTAuthentication',  # JWT认证（优先）
        'rest_framework.authentication.TokenAuthentication',  # 保留Token认证（兼容）
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '600/min',
        'login': '10/min',
        'register': '5/min',
        'ai': '20/min',
        'wallet': '30/min',
    },
}

# JWT Settings
from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),  # access_token 60分钟
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),  # refresh_token 7天
    'ROTATE_REFRESH_TOKENS': True,  # 刷新时轮换refresh_token
    'BLACKLIST_AFTER_ROTATION': True,  # 旧的refresh_token加入黑名单
    'UPDATE_LAST_LOGIN': True,  # 更新最后登录时间

    'ALGORITHM': 'HS256',
    'SIGNING_KEY': JWT_SIGNING_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    'JWK_URL': None,
    'LEEWAY': 0,

    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'USER_AUTHENTICATION_RULE': 'rest_framework_simplejwt.authentication.default_user_authentication_rule',

    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
    'TOKEN_USER_CLASS': 'rest_framework_simplejwt.models.TokenUser',

    'JTI_CLAIM': 'jti',

    'SLIDING_TOKEN_REFRESH_EXP_CLAIM': 'refresh_exp',
    'SLIDING_TOKEN_LIFETIME': timedelta(minutes=5),
    'SLIDING_TOKEN_REFRESH_LIFETIME': timedelta(days=1),
}

# CSRF Settings - 根据DEBUG模式设置
# 说明：CSRF cookie 必须可被前端 JS 读取（双提交模式），所以 HTTPONLY 始终为 False。
# 真正的安全保障来自 SameSite + Secure + 服务端比对。
CSRF_USE_SESSIONS = False
CSRF_COOKIE_HTTPONLY = False
if DEBUG:
    CSRF_COOKIE_SECURE = False
    CSRF_COOKIE_SAMESITE = 'Lax'
else:
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_SAMESITE = 'Strict'

SESSION_COOKIE_SECURE = config('SESSION_COOKIE_SECURE', default=not DEBUG, cast=bool)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=not DEBUG, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=0 if DEBUG else 31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = config('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=not DEBUG, cast=bool)
SECURE_HSTS_PRELOAD = config('SECURE_HSTS_PRELOAD', default=not DEBUG, cast=bool)
X_FRAME_OPTIONS = 'DENY'

# CORS Settings
cors_origins_str = config('CORS_ALLOWED_ORIGINS', default='')
parsed_cors_origins = _csv(cors_origins_str)

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'cache-control',  # 添加 SSE 需要的头部
]
CORS_EXPOSE_HEADERS = ['Content-Type', 'Cache-Control']

if DEBUG:
    # 开发环境默认允许本地地址，同时合并环境变量里的配置
    # 优先使用环境变量配置的地址，确保服务器IP优先级最高
    CORS_ALLOWED_ORIGINS = _dedupe([
        *parsed_cors_origins,  # 环境变量配置的地址优先
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ])
else:
    if not parsed_cors_origins:
        raise ImproperlyConfigured('生产环境必须显式配置 CORS_ALLOWED_ORIGINS')
    CORS_ALLOWED_ORIGINS = parsed_cors_origins

# CSRF Settings
csrf_trusted_origins_str = config('CSRF_TRUSTED_ORIGINS', default='')
parsed_csrf_trusted_origins = _csv(csrf_trusted_origins_str)
if DEBUG:
    CSRF_TRUSTED_ORIGINS = _dedupe([
        *parsed_csrf_trusted_origins,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ])
else:
    CSRF_TRUSTED_ORIGINS = parsed_csrf_trusted_origins or CORS_ALLOWED_ORIGINS

# Spectacular Settings
from .spectacular import SPECTACULAR_SETTINGS  # noqa

# Ensure drf-spectacular extensions are imported and registered.
import backend.schema_extensions  # noqa: E402,F401

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://:1234@127.0.0.1:6379/0')
# 结果后端默认走 Redis（同 broker URL，性能最高）；
# 设 CELERY_RESULT_BACKEND=django-db 可切换到 DB-backed 结果存储，
# 由 django-celery-results 在 Django Admin 暴露 TaskResult 列表，便于排查。
CELERY_RESULT_BACKEND = config('CELERY_RESULT_BACKEND', default=CELERY_BROKER_URL)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# 任务一旦被 worker 接受就更新为 STARTED，便于前端轮询区分"排队 vs 执行中"。
CELERY_TASK_TRACK_STARTED = True
# 结果在 Redis / DB 中的保留时长（秒）。默认 24h。
CELERY_RESULT_EXPIRES = config('CELERY_RESULT_EXPIRES', default=24 * 3600, cast=int)
# 强制 JSON 序列化，避免反序列化时携带未授信的 pickle 负载。
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']

# 当切到 django-db 后端时，自动启用 django-celery-results 以便迁移建表 + Admin 显示。
if CELERY_RESULT_BACKEND == 'django-db' and 'django_celery_results' not in INSTALLED_APPS:
    THIRD_PARTY_APPS.append('django_celery_results')
    INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# Scheduler backend. Use "django_q2" when django-q2 is installed and configured;
# otherwise the independent scheduler app falls back to the local dispatcher.
SCHEDULER_BACKEND = config('SCHEDULER_BACKEND', default='local')
Q_CLUSTER = {
    'name': 'testhub',
    'workers': config('Q_CLUSTER_WORKERS', default=4, cast=int),
    'timeout': config('Q_CLUSTER_TIMEOUT', default=600, cast=int),
    'retry': config('Q_CLUSTER_RETRY', default=900, cast=int),
    'queue_limit': config('Q_CLUSTER_QUEUE_LIMIT', default=50, cast=int),
    'bulk': config('Q_CLUSTER_BULK', default=10, cast=int),
    'orm': 'default',
}

REQUEST_PERFORMANCE_MONITORING_ENABLED = config('REQUEST_PERFORMANCE_MONITORING_ENABLED', default=True, cast=bool)
REQUEST_PERFORMANCE_SLOW_THRESHOLD_MS = config('REQUEST_PERFORMANCE_SLOW_THRESHOLD_MS', default=1000, cast=int)
REQUEST_PERFORMANCE_EXCLUDED_PREFIXES = (
    '/static/',
    '/media/',
    '/favicon.ico',
)

# Channels Configuration
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [config('REDIS_URL', default='redis://:1234@127.0.0.1:6379/0')],
        },
    },
}

# Cache Configuration (Redis, 与 Celery broker 使用不同 DB)
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
        'TIMEOUT': 300,  # 默认缓存超时5分钟
        'KEY_PREFIX': 'testhub',
    }
}

# Email Configuration
EMAIL_BACKEND = 'apps.core.email_backend.CustomEmailBackend'
# 默认验证 SMTP 证书；内部网关确需放行时再开启。
EMAIL_INSECURE_SSL = config('EMAIL_INSECURE_SSL', default=False, cast=bool)
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_USE_SSL = config('EMAIL_USE_SSL', default=False, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='webmaster@localhost')

# For 163 email with SSL, you might need this setting
EMAIL_TIMEOUT = 30

# 确保日志目录存在
log_dir = os.path.join(BASE_DIR, 'logs')
os.makedirs(log_dir, exist_ok=True)

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'app.log'),
            'when': 'midnight',
            'backupCount': 14,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
            'maxBytes': 10 * 1024 * 1024,
            'backupCount': 5,
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
        'console': {
            'level': 'DEBUG',
            'class': 'backend.logging_utils.SafeConsoleStreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # 仅在需要单独控制 level 时再覆盖；默认全部走 root。
        'django': {
            'level': 'INFO',
            'propagate': True,
        },
    },
    'root': {
        'handlers': ['file', 'error_file', 'console'],
        'level': 'INFO',
    },
}

# SimpleUI 主题配置：仅在启用 simpleui 时合并到 settings 命名空间。
if 'simpleui' in DJANGO_APPS:
    from .simpleui_settings import *  # noqa: F401,F403
