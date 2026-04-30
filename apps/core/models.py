"""
Core 应用模型
"""
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class UnifiedNotificationConfig(models.Model):
    """统一通知配置模型 - 用于配置飞书、企微、钉钉机器人"""

    CONFIG_TYPE_CHOICES = [
        ('email', 'Email'),
        ('webhook_generic', 'Generic Webhook'),
        ('webhook_feishu', '飞书机器人'),
        ('webhook_wechat', '企业微信机器人'),
        ('webhook_dingtalk', '钉钉机器人'),
    ]

    name = models.CharField(max_length=100, verbose_name='配置名称', help_text='用于标识该通知配置的名称')
    config_type = models.CharField(max_length=20, choices=CONFIG_TYPE_CHOICES, default='webhook_feishu',
                                   verbose_name='配置类型')
    webhook_bots = models.JSONField(default=dict, blank=True, null=True, verbose_name='Webhook机器人配置',
                                    help_text='飞书、企微、钉钉机器人配置')
    is_default = models.BooleanField(default=False, verbose_name='是否默认配置')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='创建者')

    class Meta:
        db_table = 'unified_notification_configs'
        verbose_name = '统一通知配置'
        verbose_name_plural = '统一通知配置'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['config_type']),
            models.Index(fields=['is_default']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f"{self.name} - {self.get_config_type_display()}"

    def get_webhook_bots(self):
        """获取配置的所有webhook机器人"""
        bots = []
        if self.webhook_bots:
            for bot_type, bot_config in self.webhook_bots.items():
                bot_data = {
                    'type': bot_type,
                    'name': bot_config.get('name', f'{bot_type}机器人'),
                    'webhook_url': bot_config.get('webhook_url'),
                    'enabled': bot_config.get('enabled', True),
                    # 业务类型勾选框
                    'enable_ui_automation': bot_config.get('enable_ui_automation', True),
                    'enable_api_testing': bot_config.get('enable_api_testing', True)
                }
                # 钉钉机器人需要额外包含secret字段
                if bot_type == 'dingtalk' and bot_config.get('secret'):
                    bot_data['secret'] = bot_config.get('secret')
                if bot_config.get('secret') and bot_type in ['feishu', 'generic', 'webhook']:
                    bot_data['secret'] = bot_config.get('secret')
                bots.append(bot_data)
        return bots


class UnifiedNotificationTemplate(models.Model):
    EVENT_MANUAL = 'manual'
    EVENT_API_EXECUTION = 'api_execution'
    EVENT_UI_EXECUTION = 'ui_execution'
    EVENT_APP_EXECUTION = 'app_execution'
    EVENT_SCHEDULER_ALERT = 'scheduler_alert'
    EVENT_REQUIREMENT = 'requirement'

    CHANNEL_ALL = 'all'
    CHANNEL_EMAIL = 'email'
    CHANNEL_WEBHOOK = 'webhook'

    CONTENT_TEXT = 'text'
    CONTENT_MARKDOWN = 'markdown'
    CONTENT_HTML = 'html'

    EVENT_CHOICES = [
        (EVENT_MANUAL, 'Manual'),
        (EVENT_API_EXECUTION, 'API Execution'),
        (EVENT_UI_EXECUTION, 'UI Execution'),
        (EVENT_APP_EXECUTION, 'APP Execution'),
        (EVENT_SCHEDULER_ALERT, 'Scheduler Alert'),
        (EVENT_REQUIREMENT, 'Requirement Analysis'),
    ]
    CHANNEL_CHOICES = [
        (CHANNEL_ALL, 'All Channels'),
        (CHANNEL_EMAIL, 'Email'),
        (CHANNEL_WEBHOOK, 'Webhook'),
    ]
    CONTENT_CHOICES = [
        (CONTENT_TEXT, 'Text'),
        (CONTENT_MARKDOWN, 'Markdown'),
        (CONTENT_HTML, 'HTML'),
    ]

    name = models.CharField(max_length=120)
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES, default=EVENT_MANUAL)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default=CHANNEL_ALL)
    subject_template = models.CharField(max_length=255, blank=True)
    body_template = models.TextField()
    content_type = models.CharField(max_length=20, choices=CONTENT_CHOICES, default=CONTENT_MARKDOWN)
    variables_schema = models.JSONField(default=dict, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_templates',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unified_notification_templates'
        ordering = ['event_type', '-is_default', '-created_at']
        indexes = [
            models.Index(fields=['event_type', 'channel', 'is_active']),
            models.Index(fields=['is_default']),
            models.Index(fields=['created_by']),
        ]

    def __str__(self):
        return f'{self.name} ({self.event_type})'


class UnifiedNotificationSendLog(models.Model):
    STATUS_SUCCESS = 'success'
    STATUS_FAILED = 'failed'

    CHANNEL_EMAIL = 'email'
    CHANNEL_WEBHOOK = 'webhook'

    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Success'),
        (STATUS_FAILED, 'Failed'),
    ]
    CHANNEL_CHOICES = [
        (CHANNEL_EMAIL, 'Email'),
        (CHANNEL_WEBHOOK, 'Webhook'),
    ]

    config = models.ForeignKey(
        UnifiedNotificationConfig,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='send_logs',
    )
    template = models.ForeignKey(
        UnifiedNotificationTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='send_logs',
    )
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    target = models.CharField(max_length=500, blank=True)
    subject = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUCCESS)
    error_message = models.TextField(blank=True)
    attachments = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    response_status = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notification_send_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'unified_notification_send_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['channel', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['config', '-created_at']),
            models.Index(fields=['template', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
        ]

    def __str__(self):
        return f'{self.channel}:{self.status}:{self.target}'


class UnifiedScheduledJobRun(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_SKIPPED = 'skipped'

    TRIGGER_MANUAL = 'manual'
    TRIGGER_SCHEDULER = 'scheduler'
    TRIGGER_RETRY = 'retry'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_SKIPPED, 'Skipped'),
    ]

    TRIGGER_CHOICES = [
        (TRIGGER_MANUAL, 'Manual'),
        (TRIGGER_SCHEDULER, 'Scheduler'),
        (TRIGGER_RETRY, 'Retry'),
    ]

    module = models.CharField(max_length=80)
    source_id = models.PositiveIntegerField()
    job_name = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    attempt = models.PositiveIntegerField(default=1)
    max_attempts = models.PositiveIntegerField(default=1)
    trigger_source = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default=TRIGGER_MANUAL)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    worker_id = models.CharField(max_length=120, blank=True)
    retry_of = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='retry_runs',
    )
    result = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unified_scheduled_job_runs',
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unified_scheduled_job_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['module', 'source_id', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['triggered_by', '-created_at']),
            models.Index(fields=['trigger_source', '-created_at']),
            models.Index(fields=['locked_until']),
            models.Index(fields=['retry_of']),
        ]

    @property
    def job_key(self):
        return f'{self.module}:{self.source_id}'

    def __str__(self):
        return f'{self.job_key} #{self.id} {self.status}'


class UnifiedScheduledJobDependency(models.Model):
    upstream_module = models.CharField(max_length=80)
    upstream_source_id = models.PositiveIntegerField()
    downstream_module = models.CharField(max_length=80)
    downstream_source_id = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unified_scheduled_job_dependencies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unified_scheduled_job_dependencies'
        ordering = ['downstream_module', 'downstream_source_id', 'upstream_module', 'upstream_source_id']
        unique_together = [
            'upstream_module',
            'upstream_source_id',
            'downstream_module',
            'downstream_source_id',
        ]
        indexes = [
            models.Index(fields=['downstream_module', 'downstream_source_id', 'is_active']),
            models.Index(fields=['upstream_module', 'upstream_source_id', 'is_active']),
        ]

    @property
    def upstream_key(self):
        return f'{self.upstream_module}:{self.upstream_source_id}'

    @property
    def downstream_key(self):
        return f'{self.downstream_module}:{self.downstream_source_id}'

    def __str__(self):
        return f'{self.upstream_key} -> {self.downstream_key}'


class UnifiedAuditLog(models.Model):
    ACTION_CREATE = 'create'
    ACTION_UPDATE = 'update'
    ACTION_DELETE = 'delete'
    ACTION_RUN = 'run'
    ACTION_PAUSE = 'pause'
    ACTION_RESUME = 'resume'

    ACTION_CHOICES = [
        (ACTION_CREATE, 'Create'),
        (ACTION_UPDATE, 'Update'),
        (ACTION_DELETE, 'Delete'),
        (ACTION_RUN, 'Run'),
        (ACTION_PAUSE, 'Pause'),
        (ACTION_RESUME, 'Resume'),
    ]

    domain = models.CharField(max_length=80, db_index=True)
    action = models.CharField(max_length=40, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=80, db_index=True)
    object_id = models.CharField(max_length=80, blank=True)
    object_name = models.CharField(max_length=255, blank=True)
    module = models.CharField(max_length=80, blank=True, db_index=True)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    project_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    project_name = models.CharField(max_length=255, blank=True)
    summary = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='unified_audit_logs',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'unified_audit_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['domain', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['module', 'source_id', '-created_at']),
            models.Index(fields=['actor', '-created_at']),
        ]

    @property
    def job_key(self):
        if self.module and self.source_id:
            return f'{self.module}:{self.source_id}'
        return ''

    def __str__(self):
        return f'{self.domain}:{self.action}:{self.object_type}:{self.object_id}'


class UnifiedSchedulerAlert(models.Model):
    STATUS_OPEN = 'open'
    STATUS_ACKNOWLEDGED = 'acknowledged'
    STATUS_RESOLVED = 'resolved'

    STATUS_CHOICES = [
        (STATUS_OPEN, 'Open'),
        (STATUS_ACKNOWLEDGED, 'Acknowledged'),
        (STATUS_RESOLVED, 'Resolved'),
    ]

    SEVERITY_INFO = 'info'
    SEVERITY_WARNING = 'warning'
    SEVERITY_DANGER = 'danger'
    SEVERITY_CRITICAL = 'critical'
    SEVERITY_CHOICES = [
        (SEVERITY_INFO, 'Info'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_DANGER, 'Danger'),
        (SEVERITY_CRITICAL, 'Critical'),
    ]

    alert_key = models.CharField(max_length=180, unique=True, db_index=True)
    alert_type = models.CharField(max_length=80, db_index=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, db_index=True)
    module = models.CharField(max_length=80, blank=True, db_index=True)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    job_key = models.CharField(max_length=100, blank=True, db_index=True)
    job_name = models.CharField(max_length=255, blank=True)
    project_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    project_name = models.CharField(max_length=255, blank=True)
    message = models.CharField(max_length=500, blank=True)
    details = models.JSONField(default=dict, blank=True)
    occurrences = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='acknowledged_scheduler_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    last_notified_at = models.DateTimeField(null=True, blank=True)
    notify_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'unified_scheduler_alerts'
        ordering = ['-last_seen_at', '-id']
        indexes = [
            models.Index(fields=['status', '-last_seen_at']),
            models.Index(fields=['severity', '-last_seen_at']),
            models.Index(fields=['project_id', '-last_seen_at']),
            models.Index(fields=['module', 'source_id', '-last_seen_at']),
        ]

    def __str__(self):
        return f'{self.alert_type}:{self.job_key or self.alert_key}:{self.status}'


class RequestPerformanceMetric(models.Model):
    method = models.CharField(max_length=12, db_index=True)
    path = models.CharField(max_length=500, db_index=True)
    route_name = models.CharField(max_length=255, blank=True, db_index=True)
    query_string = models.TextField(blank=True)
    status_code = models.PositiveIntegerField(db_index=True)
    response_time_ms = models.FloatField(db_index=True)
    request_size = models.PositiveIntegerField(default=0)
    response_size = models.PositiveIntegerField(default=0)
    is_slow = models.BooleanField(default=False, db_index=True)
    is_error = models.BooleanField(default=False, db_index=True)
    remote_addr = models.GenericIPAddressField(null=True, blank=True)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='request_performance_metrics',
    )
    user_agent = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'request_performance_metrics'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['path', '-created_at']),
            models.Index(fields=['status_code', '-created_at']),
            models.Index(fields=['is_slow', '-created_at']),
            models.Index(fields=['is_error', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]

    @property
    def status_group(self):
        return f'{int(self.status_code / 100)}xx' if self.status_code else 'unknown'

    def __str__(self):
        return f'{self.method} {self.path} {self.status_code} {self.response_time_ms:.1f}ms'
