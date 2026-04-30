from django.conf import settings
from django.db import models

from apps.projects.models import Project


class KnowledgeBase(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_ARCHIVED = 'archived'
    VECTOR_STORE_DATABASE = 'database'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_ARCHIVED, 'Archived'),
    ]

    VECTOR_STORE_CHOICES = [
        (VECTOR_STORE_DATABASE, 'Database JSON vectors'),
    ]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='knowledge_bases')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    embedding_provider = models.CharField(max_length=100, blank=True)
    embedding_model = models.CharField(max_length=200, blank=True)
    vector_store = models.CharField(max_length=50, choices=VECTOR_STORE_CHOICES, default=VECTOR_STORE_DATABASE)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='knowledge_bases')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_bases'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['embedding_provider']),
            models.Index(fields=['vector_store']),
        ]
        unique_together = ['project', 'name']

    def __str__(self):
        return self.name


class KnowledgeDocument(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_INDEXING = 'indexing'
    STATUS_INDEXED = 'indexed'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_INDEXING, 'Indexing'),
        (STATUS_INDEXED, 'Indexed'),
        (STATUS_FAILED, 'Failed'),
    ]

    SOURCE_UPLOAD = 'upload'
    SOURCE_URL = 'url'
    SOURCE_TEXT = 'text'

    SOURCE_CHOICES = [
        (SOURCE_UPLOAD, 'Upload'),
        (SOURCE_URL, 'URL'),
        (SOURCE_TEXT, 'Text'),
    ]

    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='documents')
    title = models.CharField(max_length=300)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_UPLOAD)
    source_uri = models.CharField(max_length=1000, blank=True)
    source_file = models.FileField(upload_to='knowledge_base/documents/%Y/%m/', null=True, blank=True)
    file_name = models.CharField(max_length=300, blank=True)
    file_size = models.PositiveIntegerField(default=0)
    mime_type = models.CharField(max_length=120, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    content_text = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    chunk_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='knowledge_documents')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_documents'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['knowledge_base', 'status']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['content_hash']),
        ]

    def __str__(self):
        return self.title


class KnowledgeChunk(models.Model):
    EMBEDDING_PENDING = 'pending'
    EMBEDDING_READY = 'ready'
    EMBEDDING_FAILED = 'failed'

    EMBEDDING_STATUS_CHOICES = [
        (EMBEDDING_PENDING, 'Pending'),
        (EMBEDDING_READY, 'Ready'),
        (EMBEDDING_FAILED, 'Failed'),
    ]

    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='chunks')
    chunk_index = models.PositiveIntegerField()
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    embedding_status = models.CharField(max_length=20, choices=EMBEDDING_STATUS_CHOICES, default=EMBEDDING_PENDING)
    embedding_provider = models.CharField(max_length=100, blank=True)
    embedding_model = models.CharField(max_length=200, blank=True)
    embedding_dimensions = models.PositiveIntegerField(default=0)
    embedding_ref = models.CharField(max_length=500, blank=True)
    embedding_vector = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_chunks'
        ordering = ['document_id', 'chunk_index']
        unique_together = ['document', 'chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
            models.Index(fields=['embedding_status']),
            models.Index(fields=['embedding_provider', 'embedding_model']),
        ]

    def __str__(self):
        return f'{self.document_id}:{self.chunk_index}'


class KnowledgeQuery(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ANSWERED = 'answered'
    STATUS_FAILED = 'failed'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ANSWERED, 'Answered'),
        (STATUS_FAILED, 'Failed'),
    ]

    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name='queries')
    question = models.TextField()
    answer = models.TextField(blank=True)
    citations = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='knowledge_queries')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_queries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['knowledge_base', '-created_at']),
            models.Index(fields=['created_by', '-created_at']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return self.question[:80]
