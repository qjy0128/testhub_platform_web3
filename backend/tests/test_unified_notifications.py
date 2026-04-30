from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import (
    UnifiedNotificationConfig,
    UnifiedNotificationSendLog,
    UnifiedNotificationTemplate,
)
from apps.core.notifications import (
    build_dingtalk_signed_url,
    render_notification_template,
    send_unified_notification,
)


class UnifiedNotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='notify-user', password='pass', email='user@example.com')
        self.other_user = User.objects.create_user(username='notify-other', password='pass')

    def test_template_render_supports_nested_variables(self):
        template = UnifiedNotificationTemplate.objects.create(
            name='API result',
            event_type='api_execution',
            channel='all',
            subject_template='{{ project.name }} - {{ status }}',
            body_template='Suite {{ suite }} finished in {{ metrics.duration_ms }}ms.',
            created_by=self.user,
        )

        rendered = render_notification_template(
            template,
            {
                'project': {'name': 'Star Project'},
                'status': 'passed',
                'suite': 'Smoke',
                'metrics': {'duration_ms': 123},
            },
        )

        self.assertEqual(rendered.subject, 'Star Project - passed')
        self.assertEqual(rendered.body, 'Suite Smoke finished in 123ms.')

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_unified_email_notification_sends_html_attachment_and_logs(self):
        config = UnifiedNotificationConfig.objects.create(
            name='Email config',
            config_type='email',
            webhook_bots={'email': {'recipients': ['qa@example.com']}},
            created_by=self.user,
        )
        template = UnifiedNotificationTemplate.objects.create(
            name='HTML report',
            event_type='api_execution',
            channel='email',
            subject_template='Report {{ run_id }}',
            body_template='<h1>{{ status }}</h1>',
            content_type='html',
            created_by=self.user,
        )

        logs = send_unified_notification(
            config,
            template,
            variables={'run_id': 'R-1', 'status': 'Passed'},
            attachments=[
                {
                    'filename': 'report.html',
                    'content': '<html>ok</html>',
                    'content_type': 'text/html',
                }
            ],
            created_by=self.user,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, 'Report R-1')
        self.assertEqual(mail.outbox[0].attachments[0][0], 'report.html')
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].status, UnifiedNotificationSendLog.STATUS_SUCCESS)
        self.assertEqual(logs[0].attachments[0]['filename'], 'report.html')

    def test_dingtalk_webhook_signing_and_send_log(self):
        config = UnifiedNotificationConfig.objects.create(
            name='DingTalk config',
            config_type='webhook_dingtalk',
            webhook_bots={
                'dingtalk': {
                    'webhook_url': 'https://example.com/hook',
                    'secret': 'SEC000',
                    'enabled': True,
                }
            },
            created_by=self.user,
        )
        template = UnifiedNotificationTemplate.objects.create(
            name='Webhook report',
            event_type='scheduler_alert',
            channel='webhook',
            subject_template='Alert',
            body_template='Job {{ job }} failed.',
            content_type='markdown',
            created_by=self.user,
        )
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None

        with patch('apps.core.notifications.requests.post', return_value=response) as post_mock:
            logs = send_unified_notification(config, template, variables={'job': 'API Job'}, created_by=self.user)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].status, UnifiedNotificationSendLog.STATUS_SUCCESS)
        args, kwargs = post_mock.call_args
        self.assertIn('timestamp=', args[0])
        self.assertIn('sign=', args[0])
        self.assertEqual(kwargs['json']['msgtype'], 'markdown')
        self.assertIn('API Job', kwargs['json']['markdown']['text'])

    @override_settings(DEBUG=False)
    def test_webhook_notification_rejects_private_runtime_url(self):
        config = UnifiedNotificationConfig.objects.create(
            name='Unsafe webhook config',
            config_type='webhook_generic',
            webhook_bots={
                'generic': {
                    'webhook_url': 'http://127.0.0.1:9000/hook',
                    'enabled': True,
                }
            },
            created_by=self.user,
        )
        template = UnifiedNotificationTemplate.objects.create(
            name='Webhook report',
            event_type='scheduler_alert',
            channel='webhook',
            subject_template='Alert',
            body_template='Job {{ job }} failed.',
            created_by=self.user,
        )

        with patch('apps.core.notifications.requests.post') as post_mock:
            logs = send_unified_notification(config, template, variables={'job': 'API Job'}, created_by=self.user)

        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0].status, UnifiedNotificationSendLog.STATUS_FAILED)
        self.assertIn('cannot target private', logs[0].error_message)
        post_mock.assert_not_called()

    @patch('apps.core.notifications.time.time', return_value=1234.56)
    def test_build_dingtalk_signed_url_is_stable_shape(self, _):
        signed_url = build_dingtalk_signed_url('https://example.com/hook?access_token=abc', 'SEC000')

        self.assertIn('access_token=abc&timestamp=1234560&sign=', signed_url)

    def test_template_render_api_and_log_visibility(self):
        template = UnifiedNotificationTemplate.objects.create(
            name='Manual template',
            event_type='manual',
            channel='email',
            subject_template='Hello {{ username }}',
            body_template='Hi {{ username }}',
            created_by=self.user,
        )
        UnifiedNotificationSendLog.objects.create(
            template=template,
            channel='email',
            target='qa@example.com',
            subject='Hello',
            content='Hi',
            status='success',
            created_by=self.user,
        )
        UnifiedNotificationSendLog.objects.create(
            channel='email',
            target='hidden@example.com',
            subject='Hidden',
            content='Hidden',
            status='success',
            created_by=self.other_user,
        )
        self.client.force_authenticate(user=self.user)

        render_response = self.client.post(
            f'/api/core/notification-templates/{template.id}/render/',
            {'variables': {'username': 'Ada'}},
            format='json',
        )
        logs_response = self.client.get('/api/core/notification-send-logs/')

        self.assertEqual(render_response.status_code, 200)
        self.assertEqual(render_response.data['subject'], 'Hello Ada')
        self.assertEqual(logs_response.status_code, 200)
        logs = logs_response.data.get('results', logs_response.data)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]['target'], 'qa@example.com')
