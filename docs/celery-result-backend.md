# Celery 任务结果存储

项目默认把任务结果存在 Redis（`CELERY_RESULT_BACKEND` 与 broker 共用 `REDIS_URL`），性能最佳；
但 Redis 后端不暴露给 Django Admin，排查时只能靠日志或 `list_allure_jobs` 这类自定义命令。

如果需要在 Admin 直接看任务历史 + 失败原因，按下面的步骤切到 DB 后端。

## 切换到 django-db 后端

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

`django-celery-results==2.5.1` 已在 `requirements.txt` 内，无需额外操作。

### 2. 在 `.env` 中开启

```ini
CELERY_RESULT_BACKEND=django-db
# 可选：调整结果保留时长（秒）
CELERY_RESULT_EXPIRES=86400
```

`backend/settings.py` 检测到 `CELERY_RESULT_BACKEND == 'django-db'` 后会自动把
`django_celery_results` 注入 `INSTALLED_APPS`。

### 3. 应用迁移

```bash
python manage.py migrate django_celery_results
```

会建出 `django_celery_results_taskresult` / `django_celery_results_groupresult` 等表。

### 4. 重启 Celery worker

```bash
celery -A backend worker -l info
```

### 5. 验证

- 提交一个任务（例如触发 Allure 报告生成）：
  ```http
  POST /api/api-testing/test-executions/<id>/generate-allure-report/
  ```
- 打开 Django Admin → `Celery Results > Task results`，能看到任务的：
  - `task_id` / `task_name` / `status`
  - `result` / `traceback`
  - `date_done`

也可在 shell 里直接查：

```python
from django_celery_results.models import TaskResult
TaskResult.objects.filter(status='FAILURE').order_by('-date_done')[:10]
```

## 已开启的相关配置

| 设置 | 默认 | 说明 |
|---|---|---|
| `CELERY_TASK_TRACK_STARTED` | `True` | worker 接受任务即标记 STARTED，区分排队 vs 执行 |
| `CELERY_RESULT_EXPIRES` | `86400` | 结果保留时长（秒） |
| `CELERY_TASK_SERIALIZER` | `json` | 关闭 pickle，避免反序列化漏洞 |
| `CELERY_RESULT_SERIALIZER` | `json` | 同上 |
| `CELERY_ACCEPT_CONTENT` | `['json']` | worker 仅接受 JSON 任务负载 |

## 现有自定义视图

业务侧的 Allure 报告生成任务**不依赖** `CELERY_RESULT_BACKEND`，
状态直接落在 [TestExecution](apps/api_testing/models.py) 的 `report_status` 字段上：

```bash
python manage.py list_allure_jobs --limit 50 --status FAILED
```

```http
GET /api/api-testing/test-executions/<id>/allure-report-status/
```

无需切换后端就能用。
