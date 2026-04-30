from django.contrib import admin

from .models import OcrBatch, OcrEngineConfig, OcrPage, OcrTask


@admin.register(OcrEngineConfig)
class OcrEngineConfigAdmin(admin.ModelAdmin):
    list_display = ('name', 'engine_type', 'model_name', 'is_default', 'is_active', 'created_by', 'created_at')
    list_filter = ('engine_type', 'is_default', 'is_active', 'created_at')
    search_fields = ('name', 'model_name', 'base_url')


@admin.register(OcrTask)
class OcrTaskAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'engine', 'source_type', 'status', 'created_by', 'created_at')
    list_filter = ('source_type', 'status', 'created_at')
    search_fields = ('name', 'original_filename', 'input_url', 'extracted_text')


@admin.register(OcrBatch)
class OcrBatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'project', 'engine', 'status', 'total_tasks', 'created_by', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('name',)


@admin.register(OcrPage)
class OcrPageAdmin(admin.ModelAdmin):
    list_display = ('task', 'page_number', 'confidence', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('task__name', 'text')
