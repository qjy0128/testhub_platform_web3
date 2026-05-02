"""``TestCaseGenerationTaskViewSet.stream_progress_sse`` 的方法体。"""
from __future__ import annotations

import json
import logging
import time

from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse

from ..models import TestCaseGenerationTask

logger = logging.getLogger(__name__)


def handle_stream_progress_sse(view, request, task_id=None):
    """实现 ``GET /api/requirement-analysis/testcase-generation/{task_id}/stream_progress/``。"""
    """
    SSE流式进度推送接口
    实时推送任务的流式输出和进度更新
    不使用DRF的Response，避免content negotiation问题
    注意：EventSource不支持自定义headers，无法发送JWT token，所以允许通过session cookie访问
    """
    try:
        # 记录请求信息（用于调试）
        request_origin = request.META.get('HTTP_ORIGIN', 'unknown')
        logger.info(
            f"SSE连接请求: task_id={task_id}, user={request.user}, authenticated={request.user.is_authenticated}, path={request.path}, origin={request_origin}")

        # 动态获取CORS origin - 使用 Django 配置优先
        def get_allowed_origin(origin):
            """获取允许的CORS origin，优先使用 settings 配置"""
            if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
                return origin or '*'

            allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', []) or []
            if origin in allowed_origins:
                return origin

            # 兼容未配置时的本地开发默认
            local_defaults = ['http://localhost:3000', 'http://127.0.0.1:3000']
            if settings.DEBUG and origin in local_defaults:
                return origin

            # 未匹配时返回已配置的第一个 origin，使浏览器拒绝不受信来源的凭证请求。
            if allowed_origins:
                return allowed_origins[0]

            return 'null'

        cors_origin = get_allowed_origin(request_origin)

        # 处理 CORS 预检请求
        if request.method == 'OPTIONS':
            from django.http import HttpResponse
            response = HttpResponse()
            response['Access-Control-Allow-Origin'] = cors_origin
            response['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            response['Access-Control-Allow-Headers'] = 'Content-Type'
            response['Access-Control-Allow-Credentials'] = 'true'
            response['Access-Control-Max-Age'] = '86400'
            return response

        if not getattr(request.user, 'is_authenticated', False):
            from django.http import HttpResponse
            response = HttpResponse(
                json.dumps({'error': '请先登录'}),
                status=401,
                content_type='application/json'
            )
            response['Access-Control-Allow-Origin'] = cors_origin
            response['Access-Control-Allow-Credentials'] = 'true'
            return response

        # 获取任务对象。必须复用受权限过滤的 queryset，避免 task_id 成为访问令牌。
        task = view.get_queryset().filter(task_id=task_id).first()
        if not task:
            logger.warning(f"SSE连接失败: 任务未找到, task_id={task_id}")
            # 返回JSON错误而不是SSE
            from django.http import HttpResponse
            response = HttpResponse(
                json.dumps({'error': '任务未找到'}),
                status=404,
                content_type='application/json'
            )
            response['Access-Control-Allow-Origin'] = cors_origin
            response['Access-Control-Allow-Credentials'] = 'true'
            return response

        # 记录上次发送的stream_position
        last_sent_position = 0
        loop_count = 0  # 循环计数器
        last_review_length = 0  # 记录上次发送的评审内容长度
        last_final_length = 0  # 记录上次发送的最终用例长度
        last_status = ''  # 记录上次的任务状态

        def event_stream():
            nonlocal last_sent_position, loop_count, last_review_length, last_final_length, last_status

            # Performance & Timeout Optimization
            start_time = time.time()
            last_heartbeat_time = time.time()
            last_progress_hash = None
            # 1 小时兜底超时；可通过 settings.SSE_MAX_TIMEOUT_SECONDS 覆盖。
            MAX_TIMEOUT = getattr(settings, 'SSE_MAX_TIMEOUT_SECONDS', 3600)

            while True:
                loop_count += 1
                current_time = time.time()
                has_sent_data = False

                # Safety Timeout Check
                if current_time - start_time > MAX_TIMEOUT:
                    logger.error(f"SSE Connection timed out after {MAX_TIMEOUT}s: task_id={task_id}")
                    yield f"event: error\ndata: timeout\n\n"
                    break

                # 从数据库重新获取任务状态
                try:
                    task.refresh_from_db()
                except TestCaseGenerationTask.DoesNotExist:
                    yield f"event: error\ndata: task_not_found\n\n"
                    break
                except Exception as e:
                    logger.error(f"DB refresh failed: {e}")
                    time.sleep(1)
                    continue

                # 检测状态变化，如果进入revising阶段，重置last_final_length
                if task.status != last_status:
                    logger.info(f"SSE检测到状态变化: {last_status} -> {task.status}")
                    if task.status == 'revising':
                        logger.info(f"SSE: 进入revising阶段，重置last_final_length")
                        last_final_length = 0
                    last_status = task.status

                # 每30次循环记录一次日志 (Reduced frequency)
                if loop_count % 30 == 0:
                    logger.info(
                        f"SSE stream loop #{loop_count}: task_status={task.status}, progress={task.progress}%, buffer_len={len(task.stream_buffer) if task.stream_buffer else 0}")

                # 检查任务是否已完成或失败
                if task.status in ['completed', 'failed', 'cancelled']:
                    logger.info(f"SSE任务结束: status={task.status}")
                    # 发送最终状态
                    final_status = json.dumps({'type': 'status', 'status': task.status, 'progress': task.progress},
                                              ensure_ascii=False)
                    logger.info(f"SSE发送最终状态: {final_status}")
                    yield f"data: {final_status}\n\n"

                    # 如果是流式模式且有缓冲区内容，发送剩余内容
                    if task.output_mode == 'stream' and task.stream_buffer:
                        if last_sent_position < len(task.stream_buffer):
                            new_content = task.stream_buffer[last_sent_position:]
                            content_data = json.dumps({'type': 'content', 'content': new_content},
                                                      ensure_ascii=False)
                            logger.info(f"SSE发送剩余内容: {len(new_content)} 字符")
                            yield f"data: {content_data}\n\n"
                            last_sent_position = len(task.stream_buffer)

                    # 发送剩余的评审内容
                    if task.review_feedback:
                        if len(task.review_feedback) > last_review_length:
                            remaining_review = task.review_feedback[last_review_length:]
                            if remaining_review:
                                review_data = json.dumps({'type': 'review_content', 'content': remaining_review},
                                                         ensure_ascii=False)
                                logger.info(
                                    f"SSE发送剩余评审内容: {len(remaining_review)} 字符, 总长度: {len(task.review_feedback)}")
                                yield f"data: {review_data}\n\n"
                                last_review_length = len(task.review_feedback)

                    # 发送剩余的最终用例内容
                    if task.final_test_cases:
                        if len(task.final_test_cases) > last_final_length:
                            remaining_final = task.final_test_cases[last_final_length:]
                            if remaining_final:
                                final_data = json.dumps({'type': 'final_content', 'content': remaining_final},
                                                        ensure_ascii=False)
                                logger.info(
                                    f"SSE发送剩余最终用例: {len(remaining_final)} 字符, 总长度: {len(task.final_test_cases)}")
                                yield f"data: {final_data}\n\n"
                                last_final_length = len(task.final_test_cases)

                    # 发送完成信号
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    logger.info(f"SSE流结束，总循环次数: {loop_count}")

                    # 添加短暂延迟，确保done信号被发送
                    time.sleep(0.1)
                    break

                # 如果是流式模式，发送新增的内容
                if task.output_mode == 'stream' and task.stream_buffer:
                    current_position = task.stream_position
                    if current_position > last_sent_position:
                        # 提取新增内容
                        new_content = task.stream_buffer[last_sent_position:current_position]
                        if new_content:
                            content_data = json.dumps({'type': 'content', 'content': new_content},
                                                      ensure_ascii=False)
                            logger.info(f"SSE发送新增内容: {len(new_content)} 字符, 总位置: {current_position}")
                            yield f"data: {content_data}\n\n"
                            last_sent_position = current_position
                            has_sent_data = True

                # 如果是评审阶段，发送评审内容
                if task.status == 'reviewing' and task.review_feedback:
                    review_feedback = task.review_feedback
                    if review_feedback:
                        # 计算评审内容的增量
                        if len(review_feedback) > last_review_length:
                            new_review = review_feedback[last_review_length:]
                            if new_review:
                                review_data = json.dumps({'type': 'review_content', 'content': new_review},
                                                         ensure_ascii=False)
                                logger.info(f"SSE发送评审内容: {len(new_review)} 字符")
                                yield f"data: {review_data}\n\n"
                                last_review_length = len(review_feedback)
                                has_sent_data = True

                # 如果有最终用例，发送最终用例内容（在reviewing、revising或completed阶段）
                if task.status in ['reviewing', 'revising', 'completed'] and task.final_test_cases:
                    final_cases = task.final_test_cases
                    if final_cases:
                        # 计算最终用例的增量
                        if len(final_cases) > last_final_length:
                            new_final = final_cases[last_final_length:]
                            if new_final:
                                final_data = json.dumps({'type': 'final_content', 'content': new_final},
                                                        ensure_ascii=False)
                                logger.info(
                                    f"SSE发送最终用例: {len(new_final)} 字符, 总长度: {len(final_cases)}, 阶段: {task.status}")
                                yield f"data: {final_data}\n\n"
                                last_final_length = len(final_cases)
                                has_sent_data = True

                # 发送进度更新 (Optimized)
                current_progress_hash = f"{task.status}_{task.progress}"
                if current_progress_hash != last_progress_hash:
                    progress_data = json.dumps(
                        {'type': 'progress', 'status': task.status, 'progress': task.progress},
                        ensure_ascii=False)
                    yield f"data: {progress_data}\n\n"
                    last_progress_hash = current_progress_hash
                    has_sent_data = True

                # Heartbeat - 缩短心跳间隔到10秒，确保连接保活
                if has_sent_data:
                    last_heartbeat_time = current_time
                elif current_time - last_heartbeat_time >= 10:
                    yield ": keep-alive\n\n"
                    last_heartbeat_time = current_time

                # 减少休眠时间到 0.5s，提高响应速度
                time.sleep(0.5)

        # 返回SSE流式响应 - 使用更稳健的方式
        try:
            response = StreamingHttpResponse(
                event_stream(),
                content_type='text/event-stream; charset=utf-8'
            )
        except Exception as e:
            logger.error(f"创建SSE响应失败: {e}")
            raise

        # 设置SSE相关的响应头 - 确保正确处理长连接
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        response['X-Accel-Buffering'] = 'no'
        response['X-Content-Type-Options'] = 'nosniff'
        # 添加连接保持头部，防止过早断开
        # 注意：在本地开发服务器(runserver)中，wsgiref禁止手动设置Hop-by-hop headers(如Connection)
        # 只有在生产环境(Gunicorn/Nginx)下才需要显式设置
        if not settings.DEBUG:
            response['Connection'] = 'keep-alive'

        # 设置CORS头部 - 使用动态计算的cors_origin
        response['Access-Control-Allow-Origin'] = cors_origin
        response['Access-Control-Allow-Credentials'] = 'true'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Cache-Control'

        logger.info(f"SSE连接建立成功: task_id={task_id}, cors_origin={cors_origin}")
        return response

    except Exception as e:
        logger.error(f"SSE流式推送出错: {e}")
        import traceback
        traceback.print_exc()
        from django.http import HttpResponse
        # 获取允许的origin
        request_origin = request.META.get('HTTP_ORIGIN', 'unknown')

        def get_allowed_origin(origin):
            if getattr(settings, 'CORS_ALLOW_ALL_ORIGINS', False):
                return origin or '*'

            allowed_origins = getattr(settings, 'CORS_ALLOWED_ORIGINS', []) or []
            if origin in allowed_origins:
                return origin

            local_defaults = ['http://localhost:3000', 'http://127.0.0.1:3000']
            if settings.DEBUG and origin in local_defaults:
                return origin

            if allowed_origins:
                return allowed_origins[0]

            return 'null'

        cors_origin = get_allowed_origin(request_origin)
        response = HttpResponse(
            json.dumps({'error': f'流式推送失败: {str(e)}'}),
            status=500,
            content_type='application/json'
        )
        response['Access-Control-Allow-Origin'] = cors_origin
        response['Access-Control-Allow-Credentials'] = 'true'
        return response
