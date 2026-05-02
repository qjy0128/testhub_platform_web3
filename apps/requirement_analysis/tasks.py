"""``requirement_analysis`` 的 Celery 任务。

把生成任务从 view 内嵌的 ``threading.Thread + asyncio.new_event_loop`` 模式
迁移到 Celery，使任务进度仍由 ``TestCaseGenerationTask`` 模型字段维护，
但执行不再占用 Django 工作线程。
"""
from __future__ import annotations

import asyncio
import logging
import time

from asgiref.sync import sync_to_async
from celery import shared_task
from django.utils import timezone

from .models import (
    AIModelService,
    GenerationConfig,
    TestCaseGenerationTask,
)

logger = logging.getLogger(__name__)


@shared_task(name='requirement_analysis.execute_generation', bind=True, ignore_result=True)
def execute_generation_task(self, task_id: str) -> None:
    """实际执行 AI 测试用例生成 + 评审 + 改进流程。

    ``task_id`` 是 ``TestCaseGenerationTask.task_id`` 字段（UUID 字符串），
    由 ``handle_generate`` 在创建任务后通过 ``.delay(task_id)`` 派发。
    """
    try:
        task = TestCaseGenerationTask.objects.get(task_id=task_id)
    except TestCaseGenerationTask.DoesNotExist:
        logger.warning('execute_generation: task_id=%s 不存在，跳过', task_id)
        return
    try:
        # 更新任务状态
        task.status = 'generating'
        task.progress = 10
        task.save()

        # 读取生成行为配置
        # GenerationConfig 已在文件顶部 import；保留这行作为注释提示。
        gen_config = GenerationConfig.get_active_config()

        # 获取配置参数，设置默认值
        enable_auto_review = gen_config.enable_auto_review if gen_config else True
        review_timeout = gen_config.review_timeout if gen_config else 120

        logger.info(
            f"任务 {task.task_id} 使用生成配置: auto_review={enable_auto_review}, review_timeout={review_timeout}s")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # 根据输出模式选择不同的生成方式
            if task.output_mode == 'stream':
                # 流式模式：实时保存到stream_buffer
                # 生成前先设置初始状态
                task.stream_buffer = ''
                task.stream_position = 0
                task.save()

                # 定义同步保存函数
                def save_stream_buffer(content):
                    """同步保存流式内容到数据库"""
                    task.stream_buffer = content
                    task.stream_position = len(content)
                    task.last_stream_update = timezone.now()
                    task.save(update_fields=['stream_buffer', 'stream_position',
                                             'last_stream_update'])

                # 转换为异步函数
                async_save_stream_buffer = sync_to_async(save_stream_buffer)

                async def stream_callback(chunk):
                    """流式回调：实时保存每个chunk到数据库"""
                    # 先追加到内存中的buffer
                    task.stream_buffer += chunk
                    task.stream_position = len(task.stream_buffer)
                    task.last_stream_update = timezone.now()

                    # 每10个chunk或当chunk较大时保存一次
                    if task.stream_position % 500 < 20 or len(chunk) > 100:
                        try:
                            await async_save_stream_buffer(task.stream_buffer)
                        except Exception as save_error:
                            logger.warning(f"保存流式内容失败: {save_error}")

                # 生成测试用例
                task.progress = 30
                task.save()

                generated_cases = loop.run_until_complete(
                    AIModelService.generate_test_cases_stream(task, callback=stream_callback)
                )

                # 生成完成后，确保最终的流式内容被保存
                if task.stream_buffer:
                    save_stream_buffer(task.stream_buffer)

                task.generated_test_cases = generated_cases
                task.progress = 60
                task.save()

                # 流式评审和改进（根据生成配置决定是否执行）
                if enable_auto_review and task.reviewer_model_config and task.reviewer_prompt_config:
                    try:
                        task.status = 'reviewing'
                        task.progress = 70
                        task.save()

                        logger.info(f"开始流式评审任务 {task.task_id}")

                        # 评审内容缓存
                        review_buffer = []

                        def save_review_buffer(content):
                            """同步保存评审内容"""
                            task.review_feedback = content
                            task.save(update_fields=['review_feedback'])

                        async_save_review = sync_to_async(save_review_buffer)

                        async def review_stream_callback(chunk):
                            """流式评审回调"""
                            review_buffer.append(chunk)
                            current_length = sum(len(c) for c in review_buffer)

                            # 每100字符保存一次
                            if current_length % 100 < 20 or len(chunk) > 50:
                                try:
                                    content = ''.join(review_buffer)
                                    await async_save_review(content)
                                except Exception as save_error:
                                    logger.warning(f"保存评审内容失败: {save_error}")

                        try:
                            # 移除超时限制，允许大文档完整评审
                            review_feedback = loop.run_until_complete(
                                AIModelService.review_test_cases_stream(
                                    task, generated_cases, callback=review_stream_callback
                                )
                            )
                            # 保存最终评审内容
                            if review_buffer:
                                task.review_feedback = ''.join(review_buffer)
                                task.save(update_fields=['review_feedback'])
                            logger.info(f"任务 {task.task_id} 流式评审完成")

                            # 根据评审意见改进测试用例（自动执行）
                            logger.info(f"任务 {task.task_id} 开始根据评审意见改进测试用例")
                            task.status = 'revising'
                            task.progress = 85
                            task.final_test_cases = ''  # 清空，准备流式写入
                            task.save()

                            try:
                                # 定义同步保存函数
                                def save_final_buffer(content):
                                    """同步保存最终用例内容"""
                                    task.final_test_cases = content
                                    task.save(update_fields=['final_test_cases'])

                                # 转换为异步函数
                                async_save_final = sync_to_async(save_final_buffer)

                                # 创建流式回调函数，实时更新final_test_cases
                                async def final_callback(chunk):
                                    """流式回调：实时保存最终用例到数据库"""
                                    # 实时追加到final_test_cases并保存
                                    task.final_test_cases = (
                                                                    task.final_test_cases or '') + chunk

                                    # 每100字符或chunk较大时保存一次
                                    current_length = len(task.final_test_cases)
                                    if current_length % 100 < 20 or len(chunk) > 50:
                                        try:
                                            await async_save_final(task.final_test_cases)
                                        except Exception as save_error:
                                            logger.warning(f"保存最终用例失败: {save_error}")

                                # 添加超时保护，避免任务一直卡住（使用配置的超时时间）
                                try:
                                    revised_cases = loop.run_until_complete(
                                        asyncio.wait_for(
                                            AIModelService.revise_test_cases_based_on_review(
                                                task, generated_cases, task.review_feedback,
                                                callback=final_callback
                                            ),
                                            timeout=review_timeout  # 使用配置的超时时间（秒）
                                        )
                                    )
                                except asyncio.TimeoutError:
                                    logger.error(
                                        f"任务 {task.task_id} 改进阶段超时（{review_timeout}秒），使用原始用例")
                                    # 超时时使用原始生成的用例，不再抛出异常
                                    revised_cases = generated_cases
                                # 始终使用返回的完整内容，避免流式输出被截断导致数据丢失
                                # revised_cases 是完整的返回值，task.final_test_cases 只是流式回调的中间状态
                                if revised_cases and len(revised_cases) > 0:
                                    # 检测并修复不完整的最后一条用例
                                    revised_cases = AIModelService.fix_incomplete_last_case(
                                        revised_cases)

                                    # 按用例编号排序后再保存
                                    sorted_cases = AIModelService.sort_test_cases_by_id(
                                        revised_cases)
                                    # 重新编号使编号连续
                                    renumbered_cases = AIModelService.renumber_test_cases(
                                        sorted_cases)
                                    task.final_test_cases = renumbered_cases
                                    logger.info(
                                        f"任务 {task.task_id} 测试用例改进完成 (revised_cases长度: {len(revised_cases)}, 最终保存长度: {len(task.final_test_cases)})")
                                else:
                                    # 如果返回为空，保留流式回调保存的内容
                                    logger.warning(
                                        f"任务 {task.task_id} 改进返回为空，使用流式回调保存的内容 (长度: {len(task.final_test_cases) if task.final_test_cases else 0})")
                            except Exception as revise_error:
                                logger.warning(
                                    f"任务 {task.task_id} 改进测试用例失败: {revise_error}，使用原始用例")
                                # 按用例编号排序后再保存
                                sorted_cases = AIModelService.sort_test_cases_by_id(
                                    generated_cases)
                                # 重新编号使编号连续
                                task.final_test_cases = AIModelService.renumber_test_cases(
                                    sorted_cases)
                                task.save()

                        except Exception as inner_error:
                            logger.warning(
                                f"任务 {task.task_id} 流式评审过程异常: {inner_error}")
                            task.review_feedback = f"评审过程出现异常: {str(inner_error)}\n\n建议：测试用例结构完整，可以使用。"
                            # 按用例编号排序后再保存
                            sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                            # 重新编号使编号连续
                            task.final_test_cases = AIModelService.renumber_test_cases(
                                sorted_cases)
                            task.save()

                    except Exception as review_error:
                        logger.error(f"流式评审任务 {task.task_id} 失败: {review_error}")
                        # 按用例编号排序后再保存
                        sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                        task.final_test_cases = AIModelService.renumber_test_cases(sorted_cases)
                        task.review_feedback = f"评审失败: {str(review_error)}\n\n建议：测试用例结构完整，可以使用。"
                        task.save()
                else:
                    # 按用例编号排序后再保存
                    sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                    # 重新编号使编号连续
                    task.final_test_cases = AIModelService.renumber_test_cases(sorted_cases)
                    logger.info(f"任务 {task.task_id} 跳过评审，直接使用生成的测试用例")
                    task.save()

            else:
                # 完整模式：原有逻辑
                task.progress = 30
                task.save()

                generated_cases = loop.run_until_complete(
                    AIModelService.generate_test_cases(task)
                )

                task.generated_test_cases = generated_cases
                task.progress = 60
                task.save()

                # 评审和改进测试用例（根据生成配置决定是否执行）
                if enable_auto_review and task.reviewer_model_config and task.reviewer_prompt_config:
                    try:
                        task.status = 'reviewing'
                        task.progress = 70
                        task.save()

                        logger.info(f"开始评审任务 {task.task_id}")

                        # 移除超时限制，允许大文档完整评审
                        try:
                            review_feedback = loop.run_until_complete(
                                AIModelService.review_test_cases(task, generated_cases)
                            )
                            task.review_feedback = review_feedback
                            logger.info(f"任务 {task.task_id} 评审完成")

                            # 根据评审意见改进测试用例（自动执行）
                            logger.info(f"任务 {task.task_id} 开始根据评审意见改进测试用例")
                            task.status = 'revising'
                            task.progress = 85
                            task.final_test_cases = ''  # 清空，准备流式写入
                            task.save()

                            try:
                                # 定义同步保存函数
                                def save_final_buffer_full(content):
                                    """同步保存最终用例内容"""
                                    task.final_test_cases = content
                                    task.save(update_fields=['final_test_cases'])

                                # 转换为异步函数
                                async_save_final_full = sync_to_async(save_final_buffer_full)

                                # 创建流式回调函数，实时更新final_test_cases
                                async def final_callback_full(chunk):
                                    """流式回调：实时保存最终用例到数据库"""
                                    # 实时追加到final_test_cases并保存
                                    task.final_test_cases = (
                                                                    task.final_test_cases or '') + chunk

                                    # 每100字符或chunk较大时保存一次
                                    current_length = len(task.final_test_cases)
                                    if current_length % 100 < 20 or len(chunk) > 50:
                                        try:
                                            await async_save_final_full(task.final_test_cases)
                                        except Exception as save_error:
                                            logger.warning(f"保存最终用例失败: {save_error}")

                                # 添加超时保护，避免任务一直卡住（使用配置的超时时间）
                                try:
                                    revised_cases = loop.run_until_complete(
                                        asyncio.wait_for(
                                            AIModelService.revise_test_cases_based_on_review(
                                                task, generated_cases, task.review_feedback,
                                                callback=final_callback_full
                                            ),
                                            timeout=review_timeout  # 使用配置的超时时间（秒）
                                        )
                                    )
                                except asyncio.TimeoutError:
                                    logger.error(
                                        f"任务 {task.task_id} 改进阶段超时（{review_timeout}秒），使用原始用例")
                                    # 超时时使用原始生成的用例，不再抛出异常
                                    revised_cases = generated_cases
                                # 始终使用返回的完整内容，避免流式输出被截断导致数据丢失
                                # revised_cases 是完整的返回值，task.final_test_cases 只是流式回调的中间状态
                                if revised_cases and len(revised_cases) > 0:
                                    # 检测并修复不完整的最后一条用例
                                    revised_cases = AIModelService.fix_incomplete_last_case(
                                        revised_cases)

                                    # 按用例编号排序后再保存
                                    sorted_cases = AIModelService.sort_test_cases_by_id(
                                        revised_cases)
                                    # 重新编号使编号连续
                                    renumbered_cases = AIModelService.renumber_test_cases(
                                        sorted_cases)
                                    task.final_test_cases = renumbered_cases
                                    logger.info(
                                        f"任务 {task.task_id} 测试用例改进完成 (revised_cases长度: {len(revised_cases)}, 最终保存长度: {len(task.final_test_cases)})")
                                else:
                                    # 如果返回为空，保留流式回调保存的内容
                                    logger.warning(
                                        f"任务 {task.task_id} 改进返回为空，使用流式回调保存的内容 (长度: {len(task.final_test_cases) if task.final_test_cases else 0})")
                            except Exception as revise_error:
                                logger.warning(
                                    f"任务 {task.task_id} 改进测试用例失败: {revise_error}，使用原始用例")
                                # 按用例编号排序后再保存
                                sorted_cases = AIModelService.sort_test_cases_by_id(
                                    generated_cases)
                                # 重新编号使编号连续
                                task.final_test_cases = AIModelService.renumber_test_cases(
                                    sorted_cases)
                                task.save()

                        except Exception as inner_error:
                            logger.warning(f"任务 {task.task_id} 评审过程异常: {inner_error}")
                            task.review_feedback = f"评审过程出现异常: {str(inner_error)}\n\n建议：测试用例结构完整，可以使用。"
                            # 按用例编号排序后再保存
                            sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                            # 重新编号使编号连续
                            task.final_test_cases = AIModelService.renumber_test_cases(
                                sorted_cases)
                            task.save()

                    except Exception as review_error:
                        logger.error(f"评审任务 {task.task_id} 失败: {review_error}")
                        # 评审失败时，仍然使用生成的测试用例作为最终结果
                        # 按用例编号排序后再保存
                        sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                        task.final_test_cases = AIModelService.renumber_test_cases(sorted_cases)
                        task.review_feedback = f"评审失败: {str(review_error)}\n\n建议：测试用例结构完整，可以使用。"
                        task.save()
                else:
                    # 按用例编号排序后再保存
                    sorted_cases = AIModelService.sort_test_cases_by_id(generated_cases)
                    # 重新编号使编号连续
                    task.final_test_cases = AIModelService.renumber_test_cases(sorted_cases)
                    logger.info(f"任务 {task.task_id} 跳过评审，直接使用生成的测试用例")
                    task.save()

            # 完成任务
            # 注意：不要直接调用task.save()，因为这会覆盖流式回调保存的final_test_cases
            # 从数据库重新获取最新的任务对象
            task.refresh_from_db()

            task.status = 'completed'
            task.progress = 100
            task.completed_at = timezone.now()
            task.save(update_fields=['status', 'progress', 'completed_at', 'final_test_cases'])
            logger.info(f"任务 {task.task_id} 已完成")

        finally:
            try:
                # 清理异步生成器，防止 "Task was destroyed but it is pending" 警告
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception as e:
                logger.warning(f"Error shutting down asyncgens: {e}")
            finally:
                loop.close()

    except Exception as e:
        logger.error(f"生成任务执行失败: {e}")
        task.status = 'failed'
        task.error_message = str(e)
        task.save()
