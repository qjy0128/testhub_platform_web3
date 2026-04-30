from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AiTestingRunViewSet, AiTestingSummaryView, AiTestingTaskViewSet

router = DefaultRouter()
router.register(r'tasks', AiTestingTaskViewSet, basename='ai-testing-task')
router.register(r'runs', AiTestingRunViewSet, basename='ai-testing-run')

urlpatterns = [
    path('', include(router.urls)),
    path('summary/', AiTestingSummaryView.as_view(), name='ai-testing-summary'),
]
