from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.app_automation.constants import DeviceStatus
from apps.app_automation.models import AppDevice


class AppDevicePoolTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        User = get_user_model()
        self.user = User.objects.create_user(username='app-device-user', password='pass')
        self.client.force_authenticate(user=self.user)

    def test_allocate_locks_matching_device_from_pool(self):
        matching = AppDevice.objects.create(
            device_id='emulator-5554',
            name='Pixel 8',
            status=DeviceStatus.ONLINE,
            connection_type='emulator',
            pool_name='android-regression',
            capabilities={'api_level': 35, 'form_factor': 'phone'},
            last_seen_at=timezone.now(),
        )
        AppDevice.objects.create(
            device_id='tablet-01',
            status=DeviceStatus.ONLINE,
            connection_type='usb',
            pool_name='android-regression',
            capabilities={'api_level': 35, 'form_factor': 'tablet'},
        )

        response = self.client.post(
            '/api/app-automation/devices/allocate/',
            {
                'pool_name': 'android-regression',
                'capabilities': {'form_factor': 'phone'},
                'max_allocation_time': 600,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
        matching.refresh_from_db()
        self.assertEqual(matching.status, DeviceStatus.LOCKED)
        self.assertEqual(matching.locked_by, self.user)
        self.assertEqual(matching.max_allocation_time, 600)

    def test_allocate_releases_expired_lock_before_matching(self):
        device = AppDevice.objects.create(
            device_id='expired-lock',
            status=DeviceStatus.LOCKED,
            connection_type='usb',
            pool_name='default',
            locked_at=timezone.now() - timedelta(hours=9),
            max_allocation_time=60,
        )

        response = self.client.post('/api/app-automation/devices/allocate/', {}, format='json')

        self.assertEqual(response.status_code, 200)
        device.refresh_from_db()
        self.assertEqual(device.status, DeviceStatus.LOCKED)
        self.assertEqual(device.locked_by, self.user)

    def test_pool_summary_heartbeat_and_scrcpy_prepare(self):
        device = AppDevice.objects.create(
            device_id='127.0.0.1:5555',
            status=DeviceStatus.AVAILABLE,
            connection_type='remote_emulator',
            pool_name='default',
        )

        heartbeat_response = self.client.post(
            f'/api/app-automation/devices/{device.id}/heartbeat/',
            {
                'status': DeviceStatus.ONLINE,
                'pool_name': 'nightly',
                'capabilities': {'api_level': 34},
                'scrcpy_url': 'ws://preview/device-1',
            },
            format='json',
        )
        pools_response = self.client.get('/api/app-automation/devices/pools/')
        scrcpy_response = self.client.post(
            f'/api/app-automation/devices/{device.id}/scrcpy/start/',
            {
                'launch': False,
                'scrcpy_path': 'scrcpy',
                'max_size': 1280,
                'video_bitrate': '8M',
            },
            format='json',
        )

        self.assertEqual(heartbeat_response.status_code, 200)
        self.assertEqual(heartbeat_response.data['device']['pool_name'], 'nightly')
        self.assertIsNotNone(heartbeat_response.data['device']['last_seen_at'])
        self.assertEqual(pools_response.status_code, 200)
        self.assertEqual(pools_response.data['pools'][0]['pool_name'], 'nightly')
        self.assertEqual(scrcpy_response.status_code, 200)
        self.assertEqual(scrcpy_response.data['device']['scrcpy_status'], 'prepared')
        self.assertIn('--serial', scrcpy_response.data['command'])
        self.assertIn('127.0.0.1:5555', scrcpy_response.data['command'])
