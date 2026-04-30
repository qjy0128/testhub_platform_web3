from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OcrBatchViewSet, OcrEngineConfigViewSet, OcrPageViewSet, OcrServiceSummaryView, OcrTaskViewSet

router = DefaultRouter()
router.register(r'engines', OcrEngineConfigViewSet, basename='ocr-engine')
router.register(r'batches', OcrBatchViewSet, basename='ocr-batch')
router.register(r'tasks', OcrTaskViewSet, basename='ocr-task')
router.register(r'pages', OcrPageViewSet, basename='ocr-page')

urlpatterns = [
    path('', include(router.urls)),
    path('summary/', OcrServiceSummaryView.as_view(), name='ocr-service-summary'),
]
