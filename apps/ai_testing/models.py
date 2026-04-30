from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.projects.models import Project


class AiTestingTask(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'

    MODE_BROWSER_TEXT = 'browser_text'
    MODE_BROWSER_VISION = 'browser_vision'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    MODE_CHOICES = [
        (MODE_BROWSER_TEXT, 'Browser text'),
        (MODE_BROWSER_VISION, 'Browser vision'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='ai_testing_tasks')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    instruction = models.TextField()
    target_url = models.CharField(max_length=1000, blank=True)
    execution_mode = models.CharField(max_length=40, choices=MODE_CHOICES, default=MODE_BROWSER_TEXT)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    browser_config = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_testing_tasks')
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_tasks'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['execution_mode']),
        ]

    def __str__(self):
        return self.name


class AiTestingRun(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    task = models.ForeignKey(AiTestingTask, on_delete=models.CASCADE, related_name='runs')
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='ai_testing_runs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    instruction_snapshot = models.TextField(blank=True)
    target_url_snapshot = models.CharField(max_length=1000, blank=True)
    execution_mode = models.CharField(max_length=40, choices=AiTestingTask.MODE_CHOICES, default=AiTestingTask.MODE_BROWSER_TEXT)
    planned_steps = models.JSONField(default=list, blank=True)
    executed_steps = models.JSONField(default=list, blank=True)
    artifacts = models.JSONField(default=dict, blank=True)
    cost = models.JSONField(default=dict, blank=True)
    logs = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ai_testing_runs')
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_testing_runs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['task', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.task_id}:{self.status}'
