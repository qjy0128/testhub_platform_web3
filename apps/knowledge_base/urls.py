from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    KnowledgeBaseMaintenanceView,
    KnowledgeBaseSummaryView,
    KnowledgeBaseViewSet,
    KnowledgeChunkViewSet,
    KnowledgeDocumentViewSet,
    KnowledgeQueryViewSet,
)

router = DefaultRouter()
router.register(r'bases', KnowledgeBaseViewSet, basename='knowledge-base')
router.register(r'documents', KnowledgeDocumentViewSet, basename='knowledge-document')
router.register(r'chunks', KnowledgeChunkViewSet, basename='knowledge-chunk')
router.register(r'queries', KnowledgeQueryViewSet, basename='knowledge-query')

urlpatterns = [
    path('', include(router.urls)),
    path('summary/', KnowledgeBaseSummaryView.as_view(), name='knowledge-base-summary'),
    path('maintenance/index-pending/', KnowledgeBaseMaintenanceView.as_view(), name='knowledge-base-index-pending'),
]
