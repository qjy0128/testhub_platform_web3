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


SECRET_KEY = config('SECRET_KEY', default='')
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('SECRET_KEY 必须通过环境变量配置，且不能使用 Django 示例密钥')

DEBUG = config('DEBUG', default=False, cast=bool)

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

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static_files')

# 数据工厂的静态文件目录
STATIC_FILES_URL = '/static_files/'
STATIC_FILES_ROOT = os.path.join(BASE_DIR, 'static_files')

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

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
    'SIGNING_KEY': SECRET_KEY,
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
if DEBUG:
    CSRF_COOKIE_SECURE = False
    CSRF_USE_SESSIONS = False
    CSRF_COOKIE_HTTPONLY = False
    CSRF_COOKIE_SAMESITE = 'Lax'
else:
    CSRF_COOKIE_SECURE = True
    CSRF_COOKIE_HTTPONLY = True
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
SPECTACULAR_SETTINGS = {
    'TITLE': 'TestHub API',
    'DESCRIPTION': 'Test Case Management Platform API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'ENUM_NAME_OVERRIDES': {
        # request/execution/tool enums
        'ApiRequestTypeEnum': 'apps.api_testing.models.ApiRequest.REQUEST_TYPE_CHOICES',
        'AppExecutionResultEnum': 'apps.app_automation.models.AppTestSuite.EXECUTION_RESULT_CHOICES',
        'UiFrameworkEnum': 'apps.ui_automation.models.TestScript.FRAMEWORK_CHOICES',
        'DataFactoryToolScenarioEnum': 'apps.data_factory.models.DataFactoryRecord.TOOL_SCENARIOS',

        # same field name, different choice sets
        'UiElementTypeEnum': 'apps.ui_automation.models.Element.ELEMENT_TYPE_CHOICES',
        'AppElementTypeEnum': 'apps.app_automation.models.AppElement.ELEMENT_TYPE_CHOICES',
        'UiExecutionModeEnum': [('text', '文本模式'), ('vision', '视觉模式')],
        'AiTestingExecutionModeEnum': 'apps.ai_testing.models.AiTestingTask.MODE_CHOICES',
        'UiExecutionStatusEnum': 'apps.ui_automation.models.TestSuite.EXECUTION_STATUS_CHOICES',
        'AppExecutionStatusEnum': 'apps.app_automation.models.AppTestSuite.EXECUTION_STATUS_CHOICES',

        # notification/task/priority
        'ApiNotificationTypeEnum': 'apps.api_testing.models.NotificationLog.NOTIFICATION_TYPES',
        'TaskNotificationTypeEnum': 'apps.api_testing.models.TaskNotificationSetting.NOTIFICATION_TYPES',
        'UiScheduledNotificationTypeEnum': 'apps.ui_automation.models.UiScheduledTask.NOTIFICATION_TYPE_CHOICES',
        'UiNotificationTypeEnum': 'apps.ui_automation.models.UiNotificationLog.NOTIFICATION_TYPES',
        'AppNotificationTypeEnum': 'apps.app_automation.models.AppNotificationLog.NOTIFICATION_TYPES',
        'ManualPriorityEnum': 'apps.testcases.models.TestCase.PRIORITY_CHOICES',
        'ReviewPriorityEnum': 'apps.reviews.models.TestCaseReview.PRIORITY_CHOICES',
        'RequirementPriorityEnum': 'apps.requirement_analysis.models.GeneratedTestCase.PRIORITY_CHOICES',
        'UiPriorityEnum': 'apps.ui_automation.models.TestCase.PRIORITY_CHOICES',
        'RequirementTaskTypeEnum': 'apps.requirement_analysis.models.AnalysisTask.TASK_TYPE_CHOICES',
        'ApiTaskTypeEnum': 'apps.api_testing.models.ScheduledTask.TASK_TYPE_CHOICES',
        'UiTaskTypeEnum': 'apps.ui_automation.models.UiScheduledTask.TASK_TYPE_CHOICES',

        # status enums used across modules
        'ProjectStatusEnum': 'apps.projects.models.Project.STATUS_CHOICES',
        'ManualTestCaseStatusEnum': 'apps.testcases.models.TestCase.STATUS_CHOICES',
        'TestRunStatusEnum': 'apps.executions.models.TestRun.STATUS_CHOICES',
        'TestRunCaseStatusEnum': 'apps.executions.models.TestRunCase.STATUS_CHOICES',
        'ReviewStatusEnum': 'apps.reviews.models.TestCaseReview.STATUS_CHOICES',
        'ReviewAssignmentStatusEnum': 'apps.reviews.models.ReviewAssignment.STATUS_CHOICES',
        'RequirementDocumentStatusEnum': 'apps.requirement_analysis.models.RequirementDocument.STATUS_CHOICES',
        'GeneratedCaseStatusEnum': 'apps.requirement_analysis.models.GeneratedTestCase.STATUS_CHOICES',
        'RequirementTaskStatusEnum': 'apps.requirement_analysis.models.AnalysisTask.STATUS_CHOICES',
        'GenerationTaskStatusEnum': 'apps.requirement_analysis.models.TestCaseGenerationTask.STATUS_CHOICES',
        'ApiProjectStatusEnum': 'apps.api_testing.models.ApiProject.STATUS_CHOICES',
        'ApiExecutionStatusEnum': 'apps.api_testing.models.TestExecution.EXECUTION_STATUS_CHOICES',
        'ApiScheduledTaskStatusEnum': 'apps.api_testing.models.ScheduledTask.STATUS_CHOICES',
        'ApiTaskExecutionStatusEnum': 'apps.api_testing.models.TaskExecutionLog.STATUS_CHOICES',
        'ApiNotificationStatusEnum': 'apps.api_testing.models.NotificationLog.STATUS_CHOICES',
        'UiExecutionRecordStatusEnum': 'apps.ui_automation.models.TestExecution.STATUS_CHOICES',
        'UiCaseStatusEnum': 'apps.ui_automation.models.TestCase.STATUS_CHOICES',
        'UiCaseExecutionStatusEnum': 'apps.ui_automation.models.TestCaseExecution.STATUS_CHOICES',
        'WalletSessionStatusEnum': 'apps.ui_automation.models.WalletSession.STATUS_CHOICES',
        'UiAiExecutionStatusEnum': 'apps.ui_automation.models.AIExecutionRecord.STATUS_CHOICES',
        'AppDeviceStatusEnum': 'apps.app_automation.models.AppDevice.STATUS_CHOICES',
        'AppExecutionStatusTrackEnum': 'apps.app_automation.models.AppTestExecution.STATUS_CHOICES',
        'UnifiedSchedulerRunStatusEnum': 'apps.core.models.UnifiedScheduledJobRun.STATUS_CHOICES',
        'UnifiedSchedulerAlertStatusEnum': 'apps.core.models.UnifiedSchedulerAlert.STATUS_CHOICES',
        'AiTestingTaskStatusEnum': 'apps.ai_testing.models.AiTestingTask.STATUS_CHOICES',
        'AiTestingRunStatusEnum': 'apps.ai_testing.models.AiTestingRun.STATUS_CHOICES',
        'KnowledgeDocumentStatusEnum': 'apps.knowledge_base.models.KnowledgeDocument.STATUS_CHOICES',
        'KnowledgeQueryStatusEnum': 'apps.knowledge_base.models.KnowledgeQuery.STATUS_CHOICES',
        'OcrBatchStatusEnum': 'apps.ocr_service.models.OcrBatch.STATUS_CHOICES',
    },
}

# Ensure drf-spectacular extensions are imported and registered.
import backend.schema_extensions  # noqa: E402,F401

# Celery Configuration
CELERY_BROKER_URL = config('REDIS_URL', default='redis://:1234@127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://:1234@127.0.0.1:6379/0')
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

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

# Cache Configuration
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 默认缓存超时5分钟
    }
}

# Email Configuration
EMAIL_BACKEND = 'apps.api_testing.custom_email_backend.CustomEmailBackend'
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
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'app.log'),
            'encoding': 'utf-8',
            'formatter': 'verbose',
        },
        'error_file': {
            'level': 'ERROR',
            'class': 'logging.FileHandler',
            'filename': os.path.join(BASE_DIR, 'logs', 'error.log'),
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
        # 其他具体模块的 logger 配置
        'django': {
            'handlers': ['file', 'error_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.api_testing.views': {
            'handlers': ['file', 'error_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.data_factory.tools.json_tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.data_factory.tools.encoding_tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
        'apps.data_factory.tools': {
            'handlers': ['file', 'error_file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['file', 'error_file', 'console'],
        'level': 'INFO',
        # 'propagate': True,
    },
}

# 指定simpleui默认的主题,指定一个文件名，相对路径就从simpleui的theme目录读取
SIMPLEUI_DEFAULT_THEME = 'admin.lte.css'
# 是否显示图标
SIMPLEUI_DEFAULT_ICON = True
# 是否关闭登录页粒子效果
SIMPLEUI_LOGIN_PARTICLES = True
# 后台管理首页，可以是url或者html文件
# SIMPLEUI_HOME_PAGE = 'https://www.baidu.com/'  # 后面可以扩展为大屏显示做统计
# 自定义首页标题
# SIMPLEUI_HOME_TITLE = 'Dashboard'
# # 自定义首页图标 首页图标,支持element-ui和fontawesome的图标，参考https://fontawesome.com/icons图标
# SIMPLEUI_HOME_ICON = 'fa fa-gauge'
# 设置simpleui 点击首页图标跳转的地址
SIMPLEUI_INDEX = 'http://localhost:3000'
# 自定义后台的Logo
SIMPLEUI_LOGO = 'https://static.djangoproject.com/img/favicon.6dbf28c0650e.ico'
# 是否显示首页信息
SIMPLEUI_HOME_INFO = False
# 是否显示快捷入口
SIMPLEUI_HOME_QUICK = True
# 是否显示最近动作
SIMPLEUI_HOME_ACTION = True
# 使用分析
SIMPLEUI_ANALYSIS = False
# 离线模式
SIMPLEUI_STATIC_OFFLINE = True
# True或None 默认显示加载遮罩层，指定为False 不显示遮罩层。默认显示
SIMPLEUI_LOADING = True
# 设置菜单icon，参考https://element.eleme.cn/#/zh-CN/component/icon
SIMPLEUI_ICON = {
    # 一级菜单项
    '测试执行管理': 'el-icon-s-tools',
    '用户管理': 'el-icon-user-solid',
    '令牌黑名单': 'el-icon-warning-outline',
    '接口测试': 'el-icon-s-platform',
    '智能助手': 'el-icon-chat-dot-round',
    '用例评审管理': 'el-icon-edit-outline',
    '认证令牌': 'el-icon-key',
    '认证和授权': 'el-icon-s-check',
    '需求分析': 'el-icon-notebook-2',

    # 二级菜单项
    '测试执行': 'el-icon-s-operation',
    '测试执行历史': 'el-icon-time',
    '测试执行用例': 'el-icon-document',
    '测试计划': 'el-icon-document-checked',
    '用户': 'el-icon-user',
    '用户配置': 'el-icon-setting',
    'Blacklisted Tokens': 'el-icon-warning-outline',
    'Outstanding Tokens': 'el-icon-s-custom',
    'API请求': 'el-icon-s-promotion',
    'API集合': 'el-icon-s-grid',
    'API项目': 'el-icon-s-custom',
    '任务执行日志': 'el-icon-s-data',
    '定时任务': 'el-icon-time',
    '测试套件': 'el-icon-suitcase',
    '环境变量': 'el-icon-school',
    '请求历史': 'el-icon-odometer',
    '智能助手会话': 'el-icon-chat-dot-round',
    '智能助手消息': 'el-icon-message',
    '测试用例评审': 'el-icon-check',
    '评审分配': 'el-icon-guide',
    '评审意见': 'el-icon-s-custom',
    '评审模板': 'el-icon-document',
    'Tokens': 'el-icon-key',
    '组': 'el-icon-s-custom',
    '业务需求': 'el-icon-document-checked',
    '分析任务': 'el-icon-stopwatch',
    '生成的测试用例': 'el-icon-document',
    '需求文档': 'el-icon-document',
}

# 开发环境，暂时禁用迁移历史检查
# SILENCED_SYSTEM_CHECKS = ['django.db.migrations.InconsistentMigrationHistory']
