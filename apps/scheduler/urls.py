from django.urls import path

from .views import SchedulerCapabilitiesView, SchedulerRunDueJobsView


urlpatterns = [
    path('capabilities/', SchedulerCapabilitiesView.as_view(), name='scheduler-capabilities'),
    path('run-due/', SchedulerRunDueJobsView.as_view(), name='scheduler-run-due'),
]
