# 大文件拆分计划

项目内多个文件超过 800 行的内聚阈值，单文件维护成本极高，建议按下表分阶段拆分。**每条均不在当前修复 PR 的范围**，列入此文档以确保后续工作可逐项推进。

## 后端

### `apps/requirement_analysis/views.py` (3245 行) — ✅ 全部拆分完成

原单文件已彻底转为 `views/` 包：

| 模块 | 行数 | 内容 |
|---|---|---|
| `views/__init__.py` | 49 | 重新导出 16 个公开符号 |
| `views/_common.py` | 51 | 访问控制 helpers + `PassThroughRenderer` |
| `views/text_analysis.py` | 187 | `upload_and_analyze` + `analyze_text`（去重 + 修复不可达分支） |
| `views/documents.py` | 444 | 文档 / 分析 / 业务需求 ViewSet |
| `views/generation.py` | 191 | 测试用例 / 分析任务 ViewSet + 分页类 |
| `views/ai_models.py` | 416 | AI 模型 / Prompt / 生成配置 ViewSet |
| `views/generation_tasks.py` | **762** | `TestCaseGenerationTaskViewSet` 主体（已在 800 行红线内） |
| `views/_generate_action.py` | 539 | `generate` action 完整实现，签名 `handle_generate(view, request)` |
| `views/_sse_stream.py` | 320 | `stream_progress_sse` 完整实现，签名 `handle_stream_progress_sse(view, request, task_id)` |
| `views/_test_case_parsing.py` | 233 | 测试用例解析 / 重建 / 优先级映射纯函数 |
| `views/configs_status.py` | 213 | 配置状态 schema + ViewSet |

最大文件 762 行，全部 ≤ 800 行红线。原 3245 行单文件 → 包内 11 个文件，3405 总行（含 import 重复，可由 ruff 进一步收敛）。

### `apps/api_testing/views.py` (2935 行)

- `views/projects.py` / `collections.py` / `requests.py` / `environments.py`
- `views/suites.py` / `executions.py`（含 Allure 生成）
- `views/scheduled.py` / `notifications.py`
- `views/operation_logs.py` / `ai_service_configs.py`
- `views/dashboard.py`

### `apps/data_factory/views.py` (1151 行) 与 `apps/core/views.py` (1307 行)

按 ViewSet 拆分，规则同上。

### `apps/ui_automation/serializers.py` (1422 行) 与 `apps/ui_automation/models.py` (1234 行)

- `serializers/cases.py` / `elements.py` / `executions.py` / `scheduled.py`
- `models/cases.py` / `elements.py` / `executions.py`

模型拆分需要保留原 db_table 与 `ContentType` 不变。

## 前端

| 文件 | 行数 | 拆分建议 |
|---|---|---|
| `views/api-testing/InterfaceManagement.vue` | 4279 | 抽取 `RequestEditor.vue` / `ResponsePane.vue` / `HistorySidebar.vue` / `useRequestRunner.js` |
| `views/app-automation/test-cases/SceneBuilder.vue` | 3291 | 拆 `SceneNodeList.vue` / `SceneNodeForm.vue` / `useSceneStore.js` |
| `views/data-factory/DataFactory.vue` | 3085 | 按 tag/dataset/template 拆为 3 个子页面 |
| `views/requirement-analysis/RequirementAnalysisView.vue` | 2544 | 拆出 `DocumentList.vue` / `AnalysisDetail.vue` / `useAnalysisStream.js` |
| `views/ocr-service/OcrServiceView.vue` | 1939 | 拆 `TaskList.vue` / `BatchUpload.vue` / `EngineConfig.vue` |

## 同步要点

1. 每次只拆一个文件；
2. 拆分前先补充对应模块的 unit test，重构后 diff 不应改变行为；
3. 入口 `__init__.py` / `index.js` 重新导出原符号，保持向后兼容；
4. URL / router 不变；
5. 拆完后删除"再导出 shim"，并在下个版本归档。
