from django.conf import settings
from django.db import models

from apps.projects.models import Project


class OcrEngineConfig(models.Model):
    ENGINE_GPT4V = 'gpt4v'
    ENGINE_GLM4V = 'glm4v'
    ENGINE_EASYOCR = 'easyocr'
    ENGINE_TESSERACT = 'tesseract'
    ENGINE_CUSTOM = 'custom'

    ENGINE_CHOICES = [
        (ENGINE_GPT4V, 'GPT-4V'),
        (ENGINE_GLM4V, 'GLM-4V'),
        (ENGINE_EASYOCR, 'EasyOCR'),
        (ENGINE_TESSERACT, 'Tesseract'),
        (ENGINE_CUSTOM, 'Custom'),
    ]

    name = models.CharField(max_length=200)
    engine_type = models.CharField(max_length=30, choices=ENGINE_CHOICES)
    base_url = models.CharField(max_length=500, blank=True)
    model_name = models.CharField(max_length=200, blank=True)
    credential_ref = models.CharField(max_length=200, blank=True)
    options = models.JSONField(default=dict, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_check_result = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ocr_engine_configs')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ocr_engine_configs'
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['created_by', 'is_active']),
            models.Index(fields=['engine_type']),
            models.Index(fields=['is_default']),
            models.Index(fields=['last_checked_at']),
        ]
        unique_together = ['created_by', 'name']

    def __str__(self):
        return self.name


class OcrBatch(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_RUNNING = 'running'
    STATUS_SUCCEEDED = 'succeeded'
    STATUS_PARTIAL = 'partial'
    STATUS_FAILED = 'failed'
    STATUS_CANCELLED = 'cancelled'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_RUNNING, 'Running'),
        (STATUS_SUCCEEDED, 'Succeeded'),
        (STATUS_PARTIAL, 'Partial'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='ocr_batches')
    engine = models.ForeignKey(OcrEngineConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name='batches')
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_tasks = models.PositiveIntegerField(default=0)
    succeeded_tasks = models.PositiveIntegerField(default=0)
    failed_tasks = models.PositiveIntegerField(default=0)
    cancelled_tasks = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ocr_batches')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ocr_batches'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['engine', 'status']),
        ]

    def __str__(self):
        return self.name


class OcrTask(models.Model):
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

    SOURCE_IMAGE = 'image'
    SOURCE_PDF = 'pdf'
    SOURCE_TEXT = 'text'
    SOURCE_OTHER = 'other'

    SOURCE_CHOICES = [
        (SOURCE_IMAGE, 'Image'),
        (SOURCE_PDF, 'PDF'),
        (SOURCE_TEXT, 'Text'),
        (SOURCE_OTHER, 'Other'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, null=True, blank=True, related_name='ocr_tasks')
    batch = models.ForeignKey(OcrBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    engine = models.ForeignKey(OcrEngineConfig, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks')
    name = models.CharField(max_length=200)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_IMAGE)
    input_url = models.CharField(max_length=1000, blank=True)
    input_file = models.FileField(upload_to='ocr_service/tasks/%Y/%m/', null=True, blank=True)
    input_text = models.TextField(blank=True)
    original_filename = models.CharField(max_length=300, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    extracted_text = models.TextField(blank=True)
    result_json = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    priority = models.IntegerField(default=100)
    attempt = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='ocr_tasks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ocr_tasks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['batch', 'status']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['engine', 'status']),
            models.Index(fields=['status', 'priority', 'created_at']),
        ]

    def __str__(self):
        return self.name


class OcrPage(models.Model):
    task = models.ForeignKey(OcrTask, on_delete=models.CASCADE, related_name='pages')
    page_number = models.PositiveIntegerField()
    text = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    result_json = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ocr_pages'
        ordering = ['task_id', 'page_number']
        unique_together = ['task', 'page_number']
        indexes = [
            models.Index(fields=['task', 'page_number']),
            models.Index(fields=['page_number']),
        ]

    def __str__(self):
        return f'{self.task_id}:{self.page_number}'
