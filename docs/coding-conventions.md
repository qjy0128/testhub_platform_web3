# 编码约定（项目特定）

> 跨语言通用规则见 `~/.claude/rules`，本文件只列出与本项目历史代码风格相关的约定。

## Python / Django

### `created_at` 与 `updated_at`

- 新建模型必须使用 `auto_now_add=True` / `auto_now=True`：
  ```python
  created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
  updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
  ```
- 历史代码中存在大量 `default=timezone.now` 写法（早期模板沿用），功能等价但允许被业务代码覆盖。**不主动批量重写**（每改一处都会产出 schema 无变化的 migration）。
- 例外：如果新建迁移涉及修改这些字段，顺手改成 `auto_now_add` 即可。

### 时间戳调用

- 业务代码用 `django.utils.timezone.now()`，不要直接 `datetime.datetime.now()`（`USE_TZ=True` 下后者是 naive，跨时区会出问题）。
- 已发现的历史 naive 调用集中在 `apps/core/variable_resolver.py`、`apps/data_factory/tools/`，全部用于格式化输出而非 DB 写入，留待重写时一起改。

### Logger 字符串

- 不要在 logger 调用里用 f-string：
  ```python
  # 不要这么写：日志级别即使被过滤掉，f-string 仍会执行格式化
  logger.info(f'task {task.id} started')

  # 推荐
  logger.info('task %s started', task.id)
  ```
- 历史代码大量用 f-string，可在 ruff 规则中开 `G004` 渐进收敛（项目当前 select 中未启用）。

### 函数体内 import

- 仅在以下两种情况允许：
  1. 解决循环 import；
  2. 加载条件可选依赖（如 `apps.scheduler.services` 里的 `from django_q.tasks import async_task`）。
- 其余一律上移到模块顶部。

## API Key / Secret

- 数据库字段：使用 `apps.core.encrypted_fields.EncryptedCharField`。
- 序列化：`write_only=True` + `SerializerMethodField` masked 输出。
- 日志：禁止打印明文，必要时只打 `bool(...)` 或 `len(...)`。
- 前端：禁止 `console.log(form.api_key)`；vite 生产构建已 drop 全部 `console.*` 但开发期截图共享仍是泄漏面。

## 速率限制

- 所有调用付费 AI 服务的端点必须挂 `apps.core.throttles.AIRateThrottle`。
- 钱包 / 链上交易接口挂 `WalletRateThrottle`。
- DRF `DEFAULT_THROTTLE_RATES` 中登记的 scope 必须在至少一个视图中启用，否则视为死配置。
