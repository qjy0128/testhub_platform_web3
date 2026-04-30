from django.db import models
from django.utils import timezone
from apps.users.models import User

class Project(models.Model):
    """项目模型"""
    STATUS_CHOICES = [
        ('active', '进行中'),
        ('paused', '暂停'),
        ('completed', '已完成'),
        ('archived', '已归档'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='项目名称')
    description = models.TextField(blank=True, verbose_name='项目描述')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active', verbose_name='状态')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects', verbose_name='负责人')
    members = models.ManyToManyField(User, through='ProjectMember', related_name='joined_projects', verbose_name='成员')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    def __str__(self):
        return self.name
    
    class Meta:
        db_table = 'projects'
        verbose_name = '项目'
        verbose_name_plural = '项目'
        ordering = ['-created_at']

class ProjectMember(models.Model):
    """项目成员"""
    ROLE_CHOICES = [
        ('owner', '负责人'),
        ('admin', '管理员'),
        ('developer', '开发者'),
        ('tester', '测试者'),
        ('viewer', '观察者'),
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='tester', verbose_name='角色')
    joined_at = models.DateTimeField(default=timezone.now, verbose_name='加入时间')
    
    class Meta:
        db_table = 'project_members'
        unique_together = ['project', 'user']
        verbose_name = '项目成员'
        verbose_name_plural = '项目成员'

class ProjectEnvironment(models.Model):
    """项目环境"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='environments')
    name = models.CharField(max_length=100, verbose_name='环境名称')
    base_url = models.URLField(verbose_name='基础URL')
    description = models.TextField(blank=True, verbose_name='环境描述')
    variables = models.JSONField(default=dict, verbose_name='环境变量')
    is_default = models.BooleanField(default=False, verbose_name='是否默认')
    created_at = models.DateTimeField(default=timezone.now, verbose_name='创建时间')
    
    class Meta:
        db_table = 'project_environments'
        verbose_name = '项目环境'
        verbose_name_plural = '项目环境'


class ProjectModuleBinding(models.Model):
    MODULE_API_TESTING = 'api_testing'
    MODULE_UI_AUTOMATION = 'ui_automation'
    MODULE_APP_AUTOMATION = 'app_automation'

    MODULE_CHOICES = [
        (MODULE_API_TESTING, 'API Testing'),
        (MODULE_UI_AUTOMATION, 'UI Automation'),
        (MODULE_APP_AUTOMATION, 'APP Automation'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='module_bindings')
    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    object_id = models.PositiveIntegerField()
    display_name = models.CharField(max_length=200, blank=True, default='')
    is_primary = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_module_bindings'
        unique_together = ['module', 'object_id']
        indexes = [
            models.Index(fields=['project', 'module']),
            models.Index(fields=['module', 'object_id']),
        ]
        verbose_name = 'Project module binding'
        verbose_name_plural = 'Project module bindings'

    def __str__(self):
        return f'{self.project_id}:{self.module}:{self.object_id}'


class MetaProject(models.Model):
    NODE_META_PROJECT = 'meta_project'
    NODE_MODULE_PROJECT = 'module_project'

    NODE_TYPE_CHOICES = [
        (NODE_META_PROJECT, 'Meta Project'),
        (NODE_MODULE_PROJECT, 'Module Project'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='meta_nodes')
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        related_name='children',
        null=True,
        blank=True,
    )
    node_type = models.CharField(max_length=30, choices=NODE_TYPE_CHOICES, default=NODE_META_PROJECT)
    module = models.CharField(max_length=50, blank=True, default='')
    object_id = models.PositiveIntegerField(null=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=Project.STATUS_CHOICES, default='active')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_meta_projects')
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'meta_projects'
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['project', 'parent']),
            models.Index(fields=['project', 'module', 'object_id']),
            models.Index(fields=['owner']),
        ]

    def __str__(self):
        return self.name


class UnifiedTestAsset(models.Model):
    MODULE_MANUAL = 'manual'
    MODULE_API_TESTING = 'api_testing'
    MODULE_UI_AUTOMATION = 'ui_automation'
    MODULE_APP_AUTOMATION = 'app_automation'
    MODULE_AI_TESTING = 'ai_testing'

    ASSET_TESTCASE = 'testcase'
    ASSET_TESTSUITE = 'testsuite'
    ASSET_REVIEW = 'review'

    MODULE_CHOICES = [
        (MODULE_MANUAL, 'Manual'),
        (MODULE_API_TESTING, 'API Testing'),
        (MODULE_UI_AUTOMATION, 'UI Automation'),
        (MODULE_APP_AUTOMATION, 'APP Automation'),
        (MODULE_AI_TESTING, 'AI Testing'),
    ]

    ASSET_TYPE_CHOICES = [
        (ASSET_TESTCASE, 'Test Case'),
        (ASSET_TESTSUITE, 'Test Suite'),
        (ASSET_REVIEW, 'Review'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='unified_assets')
    module = models.CharField(max_length=50, choices=MODULE_CHOICES)
    asset_type = models.CharField(max_length=50, choices=ASSET_TYPE_CHOICES)
    object_id = models.PositiveIntegerField()
    title = models.CharField(max_length=500)
    status = models.CharField(max_length=50, blank=True, default='')
    priority = models.CharField(max_length=50, blank=True, default='')
    source_updated_at = models.DateTimeField(null=True, blank=True)
    version_label = models.CharField(max_length=100, blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'unified_test_assets'
        unique_together = ['module', 'asset_type', 'object_id']
        ordering = ['-source_updated_at', '-updated_at']
        indexes = [
            models.Index(fields=['project', 'asset_type']),
            models.Index(fields=['module', 'asset_type']),
            models.Index(fields=['status']),
            models.Index(fields=['priority']),
            models.Index(fields=['source_updated_at']),
        ]

    @property
    def asset_key(self):
        return f'{self.module}:{self.asset_type}:{self.object_id}'

    def __str__(self):
        return f'{self.asset_key} {self.title}'


class UnifiedTestAssetSnapshot(models.Model):
    asset = models.ForeignKey(UnifiedTestAsset, on_delete=models.CASCADE, related_name='snapshots')
    snapshot_hash = models.CharField(max_length=128)
    payload = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'unified_test_asset_snapshots'
        unique_together = ['asset', 'snapshot_hash']
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['asset', '-created_at']),
            models.Index(fields=['snapshot_hash']),
        ]

    def __str__(self):
        return f'{self.asset.asset_key}@{self.snapshot_hash[:12]}'


class ProjectPermissionPolicy(models.Model):
    MODULE_ANY = '*'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='permission_policies')
    module = models.CharField(max_length=50, default=MODULE_ANY)
    action = models.CharField(max_length=100)
    allowed_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    description = models.CharField(max_length=255, blank=True, default='')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_project_permission_policies')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'project_permission_policies'
        ordering = ['project_id', 'module', 'action', '-updated_at']
        unique_together = ['project', 'module', 'action']
        indexes = [
            models.Index(fields=['project', 'module', 'action']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f'{self.project_id}:{self.module}:{self.action}'
