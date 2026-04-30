import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import AppTestExecution
from .permissions import user_can_access_app_execution

logger = logging.getLogger(__name__)


@database_sync_to_async
def _user_can_subscribe_to_execution(user, execution_id):
    try:
        execution = AppTestExecution.objects.select_related(
            'user',
            'test_case__project__owner',
            'test_suite__project__owner',
        ).get(id=execution_id)
    except AppTestExecution.DoesNotExist:
        return False

    return user_can_access_app_execution(user, execution)


class AppExecutionConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        try:
            self.execution_id = self.scope["url_route"]["kwargs"]["execution_id"]
            user = self.scope.get('user')
            if not getattr(user, 'is_authenticated', False):
                await self.close()
                return

            if not await _user_can_subscribe_to_execution(user, self.execution_id):
                await self.close()
                return

            self.group_name = f"app_execution_{self.execution_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            logger.info(f"WebSocket 连接成功: execution_id={self.execution_id}")
        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            await self.close()

    async def disconnect(self, close_code):
        try:
            if hasattr(self, 'group_name'):
                await self.channel_layer.group_discard(self.group_name, self.channel_name)
                logger.info(f"WebSocket 断开: execution_id={self.execution_id}, code={close_code}")
        except Exception as e:
            logger.error(f"WebSocket 断开处理失败: {e}")

    async def execution_update(self, event):
        try:
            await self.send_json(event)
        except Exception as e:
            logger.error(f"WebSocket 推送消息失败: {e}")
