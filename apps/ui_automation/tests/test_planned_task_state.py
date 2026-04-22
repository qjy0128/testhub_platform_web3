from django.test import SimpleTestCase

from apps.ui_automation.planned_task_state import (
    get_next_active_task,
    sync_planned_task_status,
)


class PlannedTaskStateSyncTests(SimpleTestCase):
    def test_sync_marks_final_task_complete_so_no_active_task_remains(self):
        planned_tasks = [
            {'id': 1, 'description': '打开 Wallet 页面', 'status': 'pending'},
            {'id': 2, 'description': '连接 MetaMask', 'status': 'pending'},
            {'id': 3, 'description': '确认签名完成登录', 'status': 'pending'},
        ]

        sync_planned_task_status(planned_tasks, 1, 'completed')
        sync_planned_task_status(planned_tasks, 2, 'completed')

        self.assertEqual(get_next_active_task(planned_tasks)['id'], 3)

        result = sync_planned_task_status(planned_tasks, 3, 'completed')

        self.assertTrue(result['updated'])
        self.assertEqual(planned_tasks[2]['status'], 'completed')
        self.assertIsNone(get_next_active_task(planned_tasks))

    def test_sync_backfills_obvious_prior_dependency_before_current_completion(self):
        planned_tasks = [
            {'id': 1, 'description': '访问 https://safuskill.ai/login', 'status': 'pending'},
            {'id': 2, 'description': '点击 Wallet 按钮', 'status': 'pending'},
        ]

        result = sync_planned_task_status(planned_tasks, 2, 'completed')

        self.assertTrue(result['updated'])
        self.assertEqual(result['backfilled_task_ids'], [1])
        self.assertEqual(planned_tasks[0]['status'], 'completed')
        self.assertEqual(planned_tasks[1]['status'], 'completed')
        self.assertIsNone(get_next_active_task(planned_tasks))
