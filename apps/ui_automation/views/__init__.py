"""
UI Automation views package.

Re-exports every public symbol from the original monolithic views.py so that
``from .views import X`` continues to work unchanged.
"""

# ---- shared utilities & pagination ----
from ._common import (
    is_ui_automation_admin,
    accessible_ui_projects_for_user,
    accessible_test_scripts_for_user,
    accessible_test_cases_for_user,
    temporary_async_unsafe_env,
    is_retryable_mysql_error,
    extract_step_info,
    StandardPagination,
)

# ---- projects ----
from .projects import UiProjectViewSet

# ---- elements ----
from .elements import (
    LocatorStrategyViewSet,
    ElementViewSet,
    ElementGroupViewSet,
    PageObjectViewSet,
    PageObjectElementViewSet,
)

# ---- scripts ----
from .scripts import (
    TestScriptViewSet,
    ScriptStepViewSet,
    ScriptElementUsageViewSet,
)

# ---- suites ----
from .suites import TestSuiteViewSet

# ---- executions ----
from .executions import (
    TestExecutionViewSet,
    ScreenshotViewSet,
    OperationRecordViewSet,
)

# ---- test cases ----
from .cases import (
    TestCaseViewSet,
    TestCaseStepViewSet,
    TestCaseExecutionViewSet,
)

# ---- AI cases & execution helpers ----
from .ai_cases import (
    AICaseViewSet,
    AIExecutionRecordViewSet,
    STOP_SIGNALS,
    TERMINAL_TASK_STATUSES,
    ACTIVE_TASK_STATUSES,
    update_planned_task_status,
    backfill_prior_pending_tasks,
    mark_first_active_task,
    summarize_planned_tasks,
    resolve_execution_status,
    infer_wallet_action_name,
    record_wallet_action,
    append_execution_summary,
    is_infrastructure_failure,
)

# ---- scheduled tasks, notifications, dashboard ----
from .scheduled import (
    UiScheduledTaskViewSet,
    UiNotificationLogViewSet,
    UiTaskNotificationSettingViewSet,
    UiDashboardViewSet,
)

__all__ = [
    # _common
    'is_ui_automation_admin',
    'accessible_ui_projects_for_user',
    'accessible_test_scripts_for_user',
    'accessible_test_cases_for_user',
    'temporary_async_unsafe_env',
    'is_retryable_mysql_error',
    'extract_step_info',
    'StandardPagination',
    # projects
    'UiProjectViewSet',
    # elements
    'LocatorStrategyViewSet',
    'ElementViewSet',
    'ElementGroupViewSet',
    'PageObjectViewSet',
    'PageObjectElementViewSet',
    # scripts
    'TestScriptViewSet',
    'ScriptStepViewSet',
    'ScriptElementUsageViewSet',
    # suites
    'TestSuiteViewSet',
    # executions
    'TestExecutionViewSet',
    'ScreenshotViewSet',
    'OperationRecordViewSet',
    # cases
    'TestCaseViewSet',
    'TestCaseStepViewSet',
    'TestCaseExecutionViewSet',
    # AI cases
    'AICaseViewSet',
    'AIExecutionRecordViewSet',
    'STOP_SIGNALS',
    'TERMINAL_TASK_STATUSES',
    'ACTIVE_TASK_STATUSES',
    'update_planned_task_status',
    'backfill_prior_pending_tasks',
    'mark_first_active_task',
    'summarize_planned_tasks',
    'resolve_execution_status',
    'infer_wallet_action_name',
    'record_wallet_action',
    'append_execution_summary',
    'is_infrastructure_failure',
    # scheduled
    'UiScheduledTaskViewSet',
    'UiNotificationLogViewSet',
    'UiTaskNotificationSettingViewSet',
    'UiDashboardViewSet',
]
