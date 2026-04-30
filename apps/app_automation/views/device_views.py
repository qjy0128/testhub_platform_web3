# -*- coding: utf-8 -*-
"""APP设备管理视图"""
import subprocess
import base64
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
import logging

from .test_case_views import AppPagination
from ..models import AppDevice
from ..constants import DeviceStatus
from ..serializers import AppDeviceSerializer
from ..managers.device_manager import DeviceManager

logger = logging.getLogger(__name__)


def _is_staff_user(user) -> bool:
    return bool(getattr(user, 'is_staff', False) or getattr(user, 'is_superuser', False))


def _require_staff_user(user):
    if not _is_staff_user(user):
        raise PermissionDenied('Only administrators can execute local device tooling.')


def get_allowed_scrcpy_path(requested_path=None) -> str:
    requested = str(requested_path or 'scrcpy').strip() or 'scrcpy'
    allowed_paths = getattr(settings, 'APP_AUTOMATION_ALLOWED_SCRCPY_PATHS', ['scrcpy'])
    normalized_allowed = {str(path).strip() for path in allowed_paths if str(path).strip()}
    if requested not in normalized_allowed:
        raise ValidationError({'scrcpy_path': 'scrcpy_path is not allowed by server configuration.'})
    return requested


def get_adb_path() -> str:
    """
    获取 ADB 路径：优先使用数据库配置，否则使用默认值 'adb'
    """
    try:
        from ..models import AppTestConfig
        config = AppTestConfig.objects.first()
        return config.adb_path if config else 'adb'
    except Exception as e:
        logger.warning(f"获取 ADB 配置失败，使用默认路径: {e}")
        return 'adb'


class AppDeviceViewSet(viewsets.ModelViewSet):
    """APP设备管理 ViewSet"""
    queryset = AppDevice.objects.all()
    serializer_class = AppDeviceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AppPagination
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'connection_type', 'pool_name', 'scrcpy_status']
    search_fields = ['device_id', 'name']

    @action(detail=False, methods=['get'])
    def pools(self, request):
        """Return device pool health grouped by pool and status."""
        rows = (
            AppDevice.objects.values('pool_name', 'status')
            .annotate(count=Count('id'))
            .order_by('pool_name', 'status')
        )
        pools = {}
        for row in rows:
            pool_name = row['pool_name'] or 'default'
            pools.setdefault(pool_name, {
                'pool_name': pool_name,
                'total': 0,
                'available': 0,
                'online': 0,
                'locked': 0,
                'offline': 0,
            })
            pools[pool_name]['total'] += row['count']
            pools[pool_name][row['status']] = row['count']
        return Response({'pools': list(pools.values())})

    @action(detail=False, methods=['post'])
    def allocate(self, request):
        """Lock and return the first available device from a pool."""
        pool_name = request.data.get('pool_name') or 'default'
        required_capabilities = request.data.get('capabilities') or {}
        max_allocation_time = int(request.data.get('max_allocation_time') or 0)

        with transaction.atomic():
            candidates = list(
                AppDevice.objects.select_for_update()
                .filter(pool_name=pool_name)
                .order_by('locked_at', '-last_seen_at', 'id')
            )
            for device in candidates:
                if device.status == DeviceStatus.LOCKED and device.is_lock_expired():
                    device.unlock()
                if device.status not in [DeviceStatus.AVAILABLE, DeviceStatus.ONLINE]:
                    continue
                capabilities = device.capabilities or {}
                if any(capabilities.get(key) != value for key, value in required_capabilities.items()):
                    continue
                if max_allocation_time > 0:
                    device.max_allocation_time = max_allocation_time
                device.lock(request.user)
                return Response({
                    'success': True,
                    'device': AppDeviceSerializer(device).data,
                })

        return Response({
            'success': False,
            'message': 'No available device matched the requested pool and capabilities.',
        }, status=status.HTTP_409_CONFLICT)

    @action(detail=False, methods=['get'], url_path='scrcpy/capabilities')
    def scrcpy_capabilities(self, request):
        _require_staff_user(request.user)
        manager = DeviceManager(adb_path=get_adb_path())
        scrcpy_path = get_allowed_scrcpy_path(request.query_params.get('scrcpy_path'))
        return Response(manager.scrcpy_available(scrcpy_path=scrcpy_path))
    
    @action(detail=False, methods=['get'])
    def discover(self, request):
        """发现ADB设备"""
        _require_staff_user(request.user)
        try:
            adb_path = get_adb_path()
            logger.info(f"使用 ADB 路径: {adb_path}")
            
            manager = DeviceManager(adb_path=adb_path)
            devices_info = manager.list_devices()
            
            # 更新或创建设备记录
            db_devices = []
            for device_info in devices_info:
                # 判断连接类型和 IP 地址
                device_id = device_info['device_id']
                if ':' in device_id:
                    # 远程设备（IP:端口格式）
                    connection_type = 'remote_emulator'
                    ip_address = device_info.get('ip_address') or ''
                elif device_id.startswith('emulator-'):
                    # 本地模拟器 - 使用 localhost
                    connection_type = 'emulator'
                    ip_address = '127.0.0.1'
                else:
                    # USB 连接的真机
                    connection_type = 'usb'
                    ip_address = device_info.get('ip_address') or ''
                
                device, created = AppDevice.objects.update_or_create(
                    device_id=device_info['device_id'],
                    defaults={
                        'name': device_info.get('name') or '',
                        'status': device_info.get('status') or 'offline',
                        'android_version': device_info.get('android_version') or '',
                        'ip_address': ip_address,
                        'port': device_info.get('port') or 5555,
                        'connection_type': connection_type,
                        'last_seen_at': timezone.now(),
                    }
                )
                db_devices.append(device)
            
            # 返回序列化后的数据库对象
            return Response({
                'success': True,
                'message': f'发现 {len(db_devices)} 个设备',
                'devices': AppDeviceSerializer(db_devices, many=True).data
            })
        except Exception as e:
            logger.error(f"发现设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'发现设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'])
    def lock(self, request, pk=None):
        """锁定设备"""
        device = self.get_object()
        
        if device.status == 'locked':
            return Response({
                'success': False,
                'message': '设备已被锁定'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        device.lock(request.user)
        
        return Response({
            'success': True,
            'message': '设备锁定成功',
            'device': AppDeviceSerializer(device).data
        })
    
    @action(detail=True, methods=['post'])
    def unlock(self, request, pk=None):
        """释放设备"""
        device = self.get_object()
        
        if device.locked_by and device.locked_by != request.user:
            return Response({
                'success': False,
                'message': '无权释放他人锁定的设备'
            }, status=status.HTTP_403_FORBIDDEN)
        
        device.unlock()
        
        return Response({
            'success': True,
            'message': '设备释放成功',
            'device': AppDeviceSerializer(device).data
        })

    @action(detail=True, methods=['post'])
    def heartbeat(self, request, pk=None):
        """Update device liveness, pool metadata and runtime capabilities."""
        device = self.get_object()
        status_value = request.data.get('status')
        if status_value in [DeviceStatus.AVAILABLE, DeviceStatus.ONLINE, DeviceStatus.OFFLINE, DeviceStatus.LOCKED]:
            device.status = status_value
        if 'pool_name' in request.data:
            device.pool_name = request.data.get('pool_name') or 'default'
        if isinstance(request.data.get('capabilities'), dict):
            device.capabilities = request.data['capabilities']
        if isinstance(request.data.get('scrcpy_config'), dict):
            device.scrcpy_config = request.data['scrcpy_config']
        if 'scrcpy_url' in request.data:
            device.scrcpy_url = request.data.get('scrcpy_url') or ''
        device.last_seen_at = timezone.now()
        device.save()
        return Response({
            'success': True,
            'device': AppDeviceSerializer(device).data,
        })

    @action(detail=True, methods=['post'], url_path='scrcpy/start')
    def start_scrcpy(self, request, pk=None):
        """Prepare or launch a scrcpy preview session for this device."""
        device = self.get_object()
        if device.status == DeviceStatus.OFFLINE:
            return Response({
                'success': False,
                'message': 'Device is offline.',
            }, status=status.HTTP_400_BAD_REQUEST)

        launch = str(request.data.get('launch', '')).lower() in {'1', 'true', 'yes'}
        if launch:
            _require_staff_user(request.user)

        manager = DeviceManager(adb_path=get_adb_path())
        options = {
            'scrcpy_path': get_allowed_scrcpy_path(request.data.get('scrcpy_path')),
            'max_size': request.data.get('max_size'),
            'video_bitrate': request.data.get('video_bitrate'),
            'window_title': request.data.get('window_title') or f'TestHub {device.name or device.device_id}',
            'stay_awake': request.data.get('stay_awake', True),
            'turn_screen_off': request.data.get('turn_screen_off', False),
            'record_path': request.data.get('record_path'),
        }
        command = manager.build_scrcpy_command(device.device_id, **options)
        process_id = None
        if launch:
            process = manager.start_scrcpy(device.device_id, **options)
            process_id = process.pid

        device.scrcpy_status = 'running' if launch else 'prepared'
        device.scrcpy_config = {
            'command': command,
            'process_id': process_id,
            'options': options,
            'prepared_at': timezone.now().isoformat(),
        }
        device.scrcpy_url = request.data.get('scrcpy_url') or device.scrcpy_url
        device.save(update_fields=['scrcpy_status', 'scrcpy_config', 'scrcpy_url', 'updated_at'])
        return Response({
            'success': True,
            'device': AppDeviceSerializer(device).data,
            'command': command,
            'process_id': process_id,
        })

    @action(detail=True, methods=['post'], url_path='scrcpy/stop')
    def stop_scrcpy(self, request, pk=None):
        device = self.get_object()
        device.scrcpy_status = 'stopped'
        device.scrcpy_config = {
            **(device.scrcpy_config or {}),
            'stopped_at': timezone.now().isoformat(),
        }
        device.save(update_fields=['scrcpy_status', 'scrcpy_config', 'updated_at'])
        return Response({
            'success': True,
            'device': AppDeviceSerializer(device).data,
        })
    
    @action(detail=True, methods=['post'])
    def disconnect(self, request, pk=None):
        """断开远程设备连接"""
        _require_staff_user(request.user)
        device = self.get_object()
        
        # 只有远程设备可以断开
        if device.connection_type not in ['remote', 'remote_emulator']:
            return Response({
                'success': False,
                'message': '只能断开远程设备的连接'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            success = manager.disconnect_device(f'{device.ip_address}:{device.port}')
            
            if not success:
                return Response({
                    'success': False,
                    'message': '断开设备失败'
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 更新设备状态为离线
            device.status = 'offline'
            device.save()
            
            return Response({
                'success': True,
                'message': f'设备 {device.name or device.device_id} 已断开连接',
                'device': AppDeviceSerializer(device).data
            })
            
        except Exception as e:
            return Response({
                'success': False,
                'message': f'断开设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'])
    def connect(self, request):
        """连接远程设备"""
        _require_staff_user(request.user)
        try:
            ip_address = request.data.get('ip_address')
            port = request.data.get('port', 5555)
            
            if not ip_address:
                return Response({
                    'success': False,
                    'message': '请提供设备IP地址'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            adb_path = get_adb_path()
            manager = DeviceManager(adb_path=adb_path)
            device_info = manager.connect_device(ip_address, port)
            
            # 创建或更新设备记录
            device, created = AppDevice.objects.update_or_create(
                device_id=device_info['device_id'],
                defaults={
                    'name': device_info.get('name') or '',
                    'status': 'online',
                    'android_version': device_info.get('android_version', ''),
                    'ip_address': ip_address,
                    'port': port,
                    'connection_type': 'remote_emulator',
                    'last_seen_at': timezone.now(),
                }
            )
            
            return Response({
                'success': True,
                'message': '设备连接成功',
                'device': AppDeviceSerializer(device).data
            })
        except Exception as e:
            logger.error(f"连接设备失败: {str(e)}")
            return Response({
                'success': False,
                'message': f'连接设备失败: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=True, methods=['post'], url_path='screenshot')
    def screenshot(self, request, pk=None):
        """
        获取设备实时截图
        
        功能：
        1. 使用 adb screencap 获取设备截图
        2. 转换为 Base64
        3. 返回 data URL 格式
        """
        _require_staff_user(request.user)
        device = self.get_object()
        
        if device.status == 'offline':
            return Response({
                'code': 400,
                'msg': '设备离线，无法截图',
                'success': False
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            adb_path = get_adb_path()
            
            # 使用 adb screencap 命令截图
            result = subprocess.run(
                [adb_path, '-s', device.device_id, 'exec-out', 'screencap', '-p'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=10
            )
            
            if not result.stdout:
                return Response({
                    'code': 500,
                    'msg': '截图失败：无返回数据',
                    'success': False
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # 转换为 Base64
            image_base64 = base64.b64encode(result.stdout).decode('utf-8')
            
            logger.info(f"设备 {device.device_id} 截图成功")
            
            return Response({
                'code': 0,
                'msg': '截图成功',
                'success': True,
                'data': {
                    'filename': f"device_{device.id}_{int(timezone.now().timestamp())}.png",
                    'content': f"data:image/png;base64,{image_base64}",
                    'device_id': device.device_id,
                    'timestamp': int(timezone.now().timestamp())
                }
            })
            
        except subprocess.TimeoutExpired:
            logger.error(f"设备 {device.device_id} 截图超时")
            return Response({
                'code': 500,
                'msg': '截图超时，请检查设备连接',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.error(f"设备 {device.device_id} 截图失败: {str(e)}")
            return Response({
                'code': 500,
                'msg': f'截图失败: {str(e)}',
                'success': False
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
