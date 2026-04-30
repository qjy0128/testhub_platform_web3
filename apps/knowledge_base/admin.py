from django.contrib import admin

from .models import KnowledgeBase, KnowledgeChunk, KnowledgeDocument, KnowledgeQuery


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'status', 'embedding_provider', 'created_by', 'created_at')
    list_filter = ('status', 'embedding_provider', 'created_at')
    search_fields = ('name', 'description', 'project__name')


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'knowledge_base', 'status', 'source_type', 'chunk_count', 'created_by', 'created_at')
    list_filter = ('status', 'source_type', 'mime_type', 'created_at')
    search_fields = ('title', 'file_name', 'source_uri', 'knowledge_base__name')


@admin.register(KnowledgeChunk)
class KnowledgeChunkAdmin(admin.ModelAdmin):
    list_display = ('document', 'chunk_index', 'embedding_status', 'token_count', 'created_at')
    list_filter = ('embedding_status', 'created_at')
    search_fields = ('content', 'document__title')


@admin.register(KnowledgeQuery)
class KnowledgeQueryAdmin(admin.ModelAdmin):
    list_display = ('knowledge_base', 'status', 'created_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('question', 'answer', 'knowledge_base__name')
