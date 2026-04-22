from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.sax.saxutils import escape

from docx import Document
from PIL import Image


ROOT = Path(r"D:\TestHub\testhub_platform")
DOCS_DIR = ROOT / "docs"
ASSET_DIR = DOCS_DIR / "tutorial_assets"
SCREENSHOT_DIR = ASSET_DIR / "screenshots"
MARKDOWN_PATH = DOCS_DIR / "TestHub功能使用教程.md"
PPTX_PATH = DOCS_DIR / "TestHub功能使用教程.pptx"

EMU_PER_INCH = 914400
SLIDE_CX = int(13.333 * EMU_PER_INCH)
SLIDE_CY = int(7.5 * EMU_PER_INCH)


def ss(name: str) -> str:
    return str(SCREENSHOT_DIR / f"{name}.png")


def legacy_image(name: str) -> str:
    return str(ROOT / name)


SLIDES = [
    {
        "kind": "cover",
        "title": "TestHub 功能使用教程",
        "subtitle": "基于本地部署环境整理，覆盖 AI 用例生成、API 测试、UI 自动化、AI 智能模式、数据工厂、配置中心与 APP 自动化",
        "image": ss("home"),
        "points": [
            "适用对象：首次接手 TestHub 的测试、QA、产品与平台管理员。",
            "内容范围：按真实前端页面梳理入口、操作顺序、典型结果与推荐使用姿势。",
            "截图来源：2026-04-20 本地部署环境。",
        ],
        "related_pages": ["/home"],
    },
    {
        "title": "使用前准备",
        "subtitle": "登录入口与基础检查",
        "image": ss("login"),
        "points": [
            "访问地址：前端 `http://localhost:3000`，首次进入先确认后端接口已可用。",
            "登录账号请使用你本地环境中已配置的管理员账号，登录成功后会进入首页。",
            "做 AI 用例生成前，建议先去配置中心补齐 AI 模型、Prompt 与生成策略。",
            "做 UI / AI / APP 自动化前，建议确认浏览器、设备、通知与环境配置。",
            "如果某页面是空状态，这是因为当前演示环境没有业务数据，不影响功能路径理解。",
        ],
        "related_pages": ["/login", "/configuration/ai-model", "/configuration/ui-env", "/configuration/app-env"],
    },
    {
        "title": "首页与导航",
        "subtitle": "从首页快速进入各功能域",
        "image": ss("home"),
        "points": [
            "首页 8 张卡片对应平台的核心功能域：AI 用例生成、API 测试、UI 自动化、数据工厂、APP 自动化、AI 智能模式、AI 评测师、配置中心。",
            "常见使用顺序：先建项目，再准备资源（需求 / 接口 / 元素 / 用例），然后执行，最后看报告。",
            "多数业务页面会出现左侧菜单；同一模块内建议从上到下按“资源准备 -> 执行 -> 报告”顺序使用。",
            "右上角可以切换语言、查看当前登录用户和账户下拉菜单。",
            "遇到功能入口可点但页面提示未配置时，先回到配置中心完成前置项。",
        ],
        "related_pages": ["/home"],
    },
    {
        "title": "AI需求分析",
        "subtitle": "把需求描述或文档转成测试用例任务",
        "image": ss("ai_requirement_analysis"),
        "points": [
            "入口：`AI用例生成 -> AI用例生成`。",
            "支持两种输入：手工填写需求标题/描述，或上传 PDF、Word、TXT、Markdown 文档。",
            "输出模式可选“实时流式输出”或“完整输出”；前者更适合长文档，后者更适合短需求。",
            "如果首次进入弹出“开始使用 AI 用例生成功能”的检查框，点击“去配置”先补齐模型、提示词和生成策略。",
            "提交后会生成一个后台任务，后续到“AI 生成用例记录”页面追踪状态。",
        ],
        "related_pages": ["/ai-generation/requirement-analysis"],
    },
    {
        "title": "AI生成用例记录",
        "subtitle": "查看 AI 任务状态与结果",
        "image": ss("ai_generated_testcases"),
        "points": [
            "入口：`AI用例生成 -> AI生成用例记录`。",
            "可按状态筛选任务：需求分析中、用例编写中、用例评审中、已完成、失败。",
            "点“刷新”获取最新状态，适合查看长时间运行的 AI 任务。",
            "已完成的任务可继续回流到项目、测试用例、评审和执行页面做人工整理。",
            "失败任务通常优先回查模型配置、Prompt 设置和原始需求内容是否完整。",
        ],
        "related_pages": ["/ai-generation/generated-testcases", "/ai-generation/task-detail/:taskId"],
    },
    {
        "title": "项目管理",
        "subtitle": "统一承载需求、用例、版本与执行数据",
        "image": ss("ai_projects"),
        "points": [
            "入口：`AI用例生成 -> 项目管理`。",
            "点击“新建项目”创建测试项目，建议补齐项目名、描述、状态与负责人。",
            "项目是全平台的组织维度，后续版本、测试用例、评审和执行计划都尽量关联项目。",
            "列表页支持按状态筛选，适合区分在研、暂停、归档等项目。",
            "建议先建项目再导入需求或新建测试用例，避免后期大量数据补关联。",
        ],
        "related_pages": ["/ai-generation/projects"],
    },
    {
        "title": "测试用例管理",
        "subtitle": "维护人工与 AI 生成的测试用例",
        "image": ss("ai_testcases"),
        "points": [
            "入口：`AI用例生成 -> 测试用例`。",
            "点击“新建用例”进入用例表单，可维护标题、项目、版本、优先级、类型和步骤。",
            "列表页支持项目筛选和优先级筛选，便于按范围整理用例。",
            "点“导出 Excel”可把当前用例数据导出给团队评审或离线归档。",
            "AI 生成的用例建议先在这里做一次人工整理，再进入评审与执行阶段。",
        ],
        "related_pages": ["/ai-generation/testcases", "/ai-generation/testcases/create"],
    },
    {
        "title": "版本管理",
        "subtitle": "按版本归集测试范围",
        "image": ss("ai_versions"),
        "points": [
            "入口：`AI用例生成 -> 版本管理`。",
            "点击“新建版本”创建版本并关联项目，用来沉淀每次发布的测试范围。",
            "版本可以挂接测试用例，便于后续统计某个版本对应的覆盖率与执行情况。",
            "建议把版本命名与实际发布节奏保持一致，例如 `v1.2.0`、`2026Q2`。",
            "如果项目长期维护，优先建立稳定的版本规范，再做批量用例归档。",
        ],
        "related_pages": ["/ai-generation/versions"],
    },
    {
        "title": "评审管理",
        "subtitle": "组织测试用例评审流程",
        "image": ss("ai_reviews"),
        "points": [
            "入口：`AI用例生成 -> 评审管理 -> 评审列表`。",
            "点击“新建评审”创建一次评审活动，可按项目、评审人、状态进行筛选。",
            "评审列表适合跟踪评审标题、优先级、用例数量、评审进度和截止时间。",
            "推荐在用例完成初稿后发起评审，避免执行阶段才发现结构性问题。",
            "如果团队多人协作，建议统一用项目 + 截止时间管理评审节奏。",
        ],
        "related_pages": ["/ai-generation/reviews", "/ai-generation/reviews/create"],
    },
    {
        "title": "评审模板",
        "subtitle": "沉淀可复用的评审规则",
        "image": ss("ai_review_templates"),
        "points": [
            "入口：`AI用例生成 -> 评审管理 -> 评审模板`。",
            "点击“创建模板”建立标准化评审清单，例如字段完整性、步骤清晰度、边界覆盖等。",
            "模板适合在同一项目或同一业务线内反复复用，减少评审标准漂移。",
            "建议把常见驳回原因抽象成模板项，提升多轮评审效率。",
            "有了模板之后，再新建评审会更容易保持团队口径一致。",
        ],
        "related_pages": ["/ai-generation/review-templates"],
    },
    {
        "title": "测试计划",
        "subtitle": "把用例组织成可执行计划",
        "image": ss("ai_executions"),
        "points": [
            "入口：`AI用例生成 -> 测试计划`。",
            "点击“新建测试计划”建立一次执行任务，建议关联项目、版本和待执行用例集合。",
            "列表页支持项目和状态过滤，适合区分草稿、执行中、已完成等计划。",
            "测试计划是从“用例资产”到“执行结果”的关键桥梁，建议每次版本发版都创建独立计划。",
            "计划创建后，再进入执行与报告页追踪结果会更清晰。",
        ],
        "related_pages": ["/ai-generation/executions"],
    },
    {
        "title": "AI测试报告",
        "subtitle": "从计划结果回看覆盖率和趋势",
        "image": ss("ai_reports"),
        "points": [
            "入口：`AI用例生成 -> 测试报告`。",
            "报告页可按项目和时间范围查看活跃计划、用例总数、通过率、缺陷分布与趋势图。",
            "点击“导出报告”可输出当前统计结果，适合周报、版本复盘和项目汇报。",
            "如果某项目长期数据为空，通常说明计划尚未建立或未关联执行记录。",
            "建议把测试报告作为版本验收和回归结果复盘的最终落点。",
        ],
        "related_pages": ["/ai-generation/reports"],
    },
    {
        "title": "API测试仪表盘",
        "subtitle": "先看全局状态，再进入具体页面",
        "image": ss("api_dashboard"),
        "points": [
            "入口：`接口测试 -> 数据看板`。",
            "这里集中展示 API 项目数、接口数、测试套件数和执行记录数，适合作为模块总览。",
            "页面下半部会概括接口管理、自动化测试、定时任务和多维报告的能力定位。",
            "新用户建议先从看板认路，再依次进入项目管理、接口管理和自动化测试页面。",
            "如果要给团队演示接口模块，这一页最适合做首页介绍。",
        ],
        "related_pages": ["/api-testing/dashboard"],
    },
    {
        "title": "API项目管理",
        "subtitle": "先建接口项目，再挂接口树",
        "image": ss("api_projects"),
        "points": [
            "入口：`接口测试 -> 项目管理`。",
            "建议按系统、服务或产品线划分 API 项目，例如用户中心、支付中心、运营后台。",
            "接口项目是接口树、环境、自动化测试与报告的共同归属。",
            "创建项目后，再去“接口管理”里建分组和具体请求，会比后补归属更高效。",
            "如果接口很多，项目粒度不要过细，否则后期权限和统计会变碎。",
        ],
        "related_pages": ["/api-testing/projects"],
    },
    {
        "title": "接口管理",
        "subtitle": "维护请求定义、参数和断言基础",
        "image": ss("api_interfaces"),
        "points": [
            "入口：`接口测试 -> 接口管理`。",
            "在这里维护接口树、请求方法、URL、请求头、参数、Body 与说明。",
            "建议先把常用登录、鉴权、核心业务接口整理出来，再逐步补充长尾接口。",
            "接口定义完善之后，自动化测试页才能更顺畅地复用这些接口。",
            "常见做法是按业务域建目录，再在目录下按接口粒度录入请求。",
        ],
        "related_pages": ["/api-testing/interfaces"],
    },
    {
        "title": "API自动化测试",
        "subtitle": "把接口串成可执行场景",
        "image": ss("api_automation"),
        "points": [
            "入口：`接口测试 -> 自动化测试`。",
            "这里适合把多个接口按顺序编排成测试场景，加入断言、变量提取和前后置步骤。",
            "推荐先在接口管理中维护好单接口，再在这里做跨接口串联和回归场景。",
            "做自动化时优先把登录、公共鉴权和关键业务链路拆成可复用步骤。",
            "编排完成后，结合环境管理和定时任务，就能形成稳定的回归流水线。",
        ],
        "related_pages": ["/api-testing/automation"],
    },
    {
        "title": "API环境、历史与定时任务",
        "subtitle": "把单次调试变成可重复回归",
        "image": ss("api_scheduled_tasks"),
        "points": [
            "相关入口：`环境管理`、`请求历史`、`测试报告`、`定时任务`、`通知列表`。",
            "环境管理先配置 baseURL、变量、鉴权参数；请求历史用于排查单次调用细节。",
            "定时任务适合做每日巡检、冒烟回归和发布后守护；通知列表用于验证消息是否发出。",
            "报告页看成功率与趋势，历史页看单次失败原因，环境页保证不同环境可切换。",
            "推荐顺序：环境 -> 接口 -> 自动化 -> 定时任务 -> 报告 -> 通知复核。",
        ],
        "related_pages": [
            "/api-testing/environments",
            "/api-testing/history",
            "/api-testing/reports",
            "/api-testing/scheduled-tasks",
            "/api-testing/notification-logs",
        ],
    },
    {
        "title": "UI自动化仪表盘",
        "subtitle": "先看页面入口，再补资源",
        "image": ss("ui_dashboard"),
        "points": [
            "入口：`UI自动化测试 -> 数据看板`。",
            "看板适合快速了解当前项目、元素、脚本、套件、执行记录和报告的整体入口。",
            "新建 UI 自动化前，推荐先准备项目与元素，再进入用例、脚本和执行链路。",
            "如果你的目标是录入已有脚本，直接跳脚本生成或脚本列表也可以。",
            "如果你的目标是从零搭平台，建议按“项目 -> 元素 -> 用例 -> 脚本 -> 套件 -> 执行”走。",
        ],
        "related_pages": ["/ui-automation/dashboard"],
    },
    {
        "title": "UI项目与元素管理",
        "subtitle": "先定义项目，再沉淀定位元素",
        "image": ss("ui_elements"),
        "points": [
            "相关入口：`项目管理` 与 `元素管理`。",
            "元素管理是 UI 自动化的基础资产，用来维护页面元素及其定位方式。",
            "元素库准备好之后，脚本生成页可以直接从左侧元素库插入定位代码。",
            "建议按页面或业务模块来组织元素，避免元素名混乱导致脚本难维护。",
            "项目页负责承载资源归属，元素页负责承载复用定位，这两页通常一起使用。",
        ],
        "related_pages": ["/ui-automation/projects", "/ui-automation/elements-enhanced"],
    },
    {
        "title": "UI测试用例管理",
        "subtitle": "把页面操作整理成可执行用例",
        "image": ss("ui_test_cases"),
        "points": [
            "入口：`UI自动化测试 -> 用例管理`。",
            "这里适合维护 UI 用例的标题、前置条件、步骤描述和业务归属。",
            "推荐先用人工语言描述清楚场景，再进入脚本生成页做自动化实现。",
            "如果一个页面流程很长，建议拆成多个小用例，再在套件里编排执行顺序。",
            "用例页的目标是沉淀“测试意图”，脚本页的目标是沉淀“自动化实现”。",
        ],
        "related_pages": ["/ui-automation/test-cases"],
    },
    {
        "title": "UI脚本生成",
        "subtitle": "从元素库快速拼装自动化脚本",
        "image": ss("ui_scripts_enhanced"),
        "points": [
            "入口：`UI自动化测试 -> 脚本生成`。",
            "左侧是元素库，中间是脚本编辑区，右侧是执行日志；支持选择语言和执行引擎。",
            "推荐做法：先选项目，再从元素库插入关键元素，补足点击、输入、等待和断言逻辑。",
            "生成完成后点击“保存脚本”，再去脚本列表或套件页纳入统一执行。",
            "如果当前元素库为空，先回元素管理页建元素，再回来编排脚本。",
        ],
        "related_pages": ["/ui-automation/scripts-enhanced", "/ui-automation/scripts/editor"],
    },
    {
        "title": "UI脚本列表、套件与执行",
        "subtitle": "把单脚本提升为稳定回归资产",
        "image": ss("ui_executions"),
        "points": [
            "相关入口：`脚本列表`、`套件管理`、`执行记录`、`测试报告`、`定时任务`、`通知列表`。",
            "脚本列表适合管理单脚本版本；套件页适合把多个脚本按场景串起来执行。",
            "执行记录看单次结果，报告页看整体统计，定时任务负责把回归跑起来，通知页负责把结果送出去。",
            "推荐顺序：脚本保存 -> 组套件 -> 手工执行验证 -> 看报告 -> 上定时任务。",
            "如果要做 nightly 回归，这一组页面要一起配合使用。",
        ],
        "related_pages": [
            "/ui-automation/scripts",
            "/ui-automation/suites",
            "/ui-automation/executions",
            "/ui-automation/reports",
            "/ui-automation/scheduled-tasks",
            "/ui-automation/notification-logs",
        ],
    },
    {
        "title": "AI智能模式",
        "subtitle": "用自然语言直接驱动浏览器执行任务",
        "image": ss("ai_mode_testing"),
        "points": [
            "入口：`AI智能模式 -> AI智能测试`。",
            "适合没有现成脚本、但已经知道测试目标和操作步骤的场景。",
            "页面通常会要求输入任务描述、执行模式和相关参数，然后由 AI 自动规划执行路径。",
            "如果任务涉及钱包、登录、切链或签名，建议把关键步骤和限制条件写进任务文本里。",
            "首次使用前先到配置中心确认 AI 模型、浏览器环境和 AI 模式配置已经就绪。",
        ],
        "related_pages": ["/ai-intelligent-mode/testing"],
    },
    {
        "title": "AI智能用例与执行记录",
        "subtitle": "看 AI 任务沉淀与执行结果",
        "image": ss("ai_mode_execution_records"),
        "points": [
            "相关入口：`AI智能模式 -> AI用例管理` 与 `AI执行记录`。",
            "用例管理用于沉淀自然语言任务模板；执行记录用于回看每次运行的状态、日志和结果。",
            "如果一个自然语言任务已经验证可行，建议沉淀成固定用例，避免每次重写。",
            "执行记录页尤其适合排查 AI 步骤偏航、环境不稳定和登录失败问题。",
            "推荐顺序：先在测试页跑通 -> 再沉淀为 AI 用例 -> 再观察执行记录。",
        ],
        "related_pages": ["/ai-intelligent-mode/cases", "/ai-intelligent-mode/execution-records"],
    },
    {
        "title": "钱包登录实战：连接钱包",
        "subtitle": "以 SafuSkill 为例发起 MetaMask 登录",
        "image": legacy_image("tmp-safuskill-after-connect-click.png"),
        "points": [
            "站点页通常会先出现“Connect a Wallet”弹窗，左侧列出可选钱包。",
            "当前第一版建议优先使用 MetaMask 的 EVM 链流程，路径最稳定。",
            "在 AI 任务里要明确写出：连接钱包、切链、签名消息、发送交易确认等期望动作。",
            "如果站点先出现自定义“Connect Wallet”按钮，先点站点按钮，再等待钱包选择器出现。",
            "这一步的目标不是点任何随机钱包，而是精准切到 MetaMask 并进入授权链路。",
        ],
        "related_pages": ["外部站点：SafuSkill 钱包连接弹窗"],
    },
    {
        "title": "钱包登录实战：MetaMask 解锁与确认",
        "subtitle": "完成扩展侧解锁、授权和确认",
        "image": legacy_image("tmp-metamask-unlock.png"),
        "points": [
            "当 MetaMask 打开解锁页时，先输入钱包密码，再点击登录。",
            "如果后续出现连接、签名、切链或交易确认页，优先点击主确认按钮，不要盲点扩展内部元素。",
            "在当前项目里，AI 智能模式已经为钱包流程补了专门规则：解锁、确认、回站点。",
            "如果站点页空白或半加载，AI 会尝试切回前台标签页恢复，但你仍应在任务描述里写清目标地址。",
            "钱包弹窗处理完成后，再回到原站点验证是否已登录或地址是否已显示。",
        ],
        "related_pages": ["MetaMask 扩展页", "钱包授权确认页"],
    },
    {
        "title": "钱包登录实战：登录结果",
        "subtitle": "回到站点验证钱包已生效",
        "image": legacy_image("tmp-safuskill-logged-in-home.png"),
        "points": [
            "回站点后优先看右上角钱包地址、用户头像、已登录状态或权限入口是否出现。",
            "不要只看弹窗是否关闭，必须以站点状态变化作为最终验收依据。",
            "如果站点要求签名或补充授权，继续跟随站点流程完成最后一步。",
            "建议把“登录成功判定条件”写进 AI 任务描述，例如：右上角出现地址或进入个人首页。",
            "完成一次稳定流程后，可以把它沉淀到 AI 用例管理页作为可复用的钱包登录模板。",
        ],
        "related_pages": ["外部站点：SafuSkill 登录后首页"],
    },
    {
        "title": "数据工厂",
        "subtitle": "集中准备测试数据和转换工具",
        "image": ss("data_factory"),
        "points": [
            "入口：`数据工厂`。",
            "页面按“按工具分类”“按使用场景”“使用历史”组织，可承载数据生成、格式转换和加解密类工具。",
            "适合在做接口测试、UI 自动化、AI 任务时，统一准备手机号、邮箱、JSON、JWT、时间戳等数据。",
            "如果团队经常重复造测试数据，建议先把常用规则沉淀到这里，再在各模块中引用。",
            "这是全平台的共用底座，越早规范，后续自动化越省时间。",
        ],
        "related_pages": ["/data-factory"],
    },
    {
        "title": "配置中心：AI生成相关",
        "subtitle": "模型、Prompt 与生成策略要先配好",
        "image": ss("config_ai_model"),
        "points": [
            "相关入口：`AI模型配置`、`Prompt配置`、`生成配置`。",
            "AI 模型配置负责填 API Key、Base URL、模型名和角色；Prompt 配置负责定义编写与评审提示词。",
            "生成配置负责决定输出方式、自动评审等生成行为，是 AI 用例生成页的重要前置条件。",
            "如果 AI 用例生成页提示未配置，通常就是这三页至少有一项缺失。",
            "建议把生产、测试模型分开命名，并保留一套稳定模板做回退。",
        ],
        "related_pages": ["/configuration/ai-model", "/configuration/prompt-config", "/configuration/generation-config"],
    },
    {
        "title": "配置中心：UI / APP 环境与 AI 模式",
        "subtitle": "浏览器、设备和智能模式都从这里起步",
        "image": ss("config_ai_mode"),
        "points": [
            "相关入口：`UI环境配置`、`APP环境配置`、`AI模式配置`、`通知与任务配置`、`Dify配置`。",
            "UI 环境页适合检查浏览器/驱动/自动化环境；APP 环境页适合检查设备与移动端执行配置。",
            "AI 模式配置用来维护 Browser-use / 浏览器智能执行所需的模型与环境参数。",
            "通知与任务配置页用于统一消息通道；Dify 配置页用于接入外部 AI 助手能力。",
            "如果自动化跑不起来，不要先改脚本，先回配置中心排查环境和服务端配置。",
        ],
        "related_pages": [
            "/configuration/ui-env",
            "/configuration/app-env",
            "/configuration/ai-mode",
            "/configuration/scheduled-task",
            "/configuration/dify",
        ],
    },
    {
        "title": "APP自动化：总览与设备",
        "subtitle": "先看 Dashboard，再确认设备可用",
        "image": ss("app_dashboard"),
        "points": [
            "入口：`APP自动化测试 -> Dashboard`。",
            "Dashboard 会展示项目、设备、用例、执行和最近记录，适合快速判断移动端资源是否就绪。",
            "真正开始执行前，优先进入“设备管理”确认模拟器或真机在线状态。",
            "如果没有设备，后续元素采集、场景编排和执行都会被阻断。",
            "建议把设备池和项目绑定关系先规划清楚，再开展 APP 自动化建设。",
        ],
        "related_pages": ["/app-automation/dashboard", "/app-automation/devices"],
    },
    {
        "title": "APP自动化：场景编排",
        "subtitle": "把组件和步骤组合成可执行移动端流程",
        "image": ss("app_scene_builder"),
        "points": [
            "入口：`APP自动化测试 -> 用例编排`。",
            "页面上方维护场景名称、所属项目、描述、重试次数等元数据；下方把组件拖入场景步骤区域完成编排。",
            "左侧组件库承载基础组件和自定义组件，中间是场景步骤，右侧是当前步骤配置。",
            "如果需要新元素，可直接点击右侧“创建元素工具”，说明移动端元素与场景是联动设计的。",
            "推荐做法：先建元素，再建基础组件，最后在这里拼装完整业务链路。",
        ],
        "related_pages": ["/app-automation/scene-builder", "/app-automation/elements"],
    },
    {
        "title": "APP自动化：用例、套件、执行与报告",
        "subtitle": "把单场景提升为可持续回归",
        "image": ss("app_test_cases"),
        "points": [
            "相关入口：`测试用例`、`测试套件`、`执行记录`、`测试报告`、`定时任务`、`通知列表`。",
            "测试用例页沉淀单个场景，测试套件页把多个场景串成回归集合，执行记录页回看单次运行明细。",
            "报告页适合看最近执行结果和 Allure 入口，定时任务页负责把 APP 回归定时跑起来。",
            "建议先单用例跑通，再入套件，再上定时任务，最后用通知把结果发到团队。",
            "如果要做夜间巡检，这是 APP 自动化模块的最终落地链路。",
        ],
        "related_pages": [
            "/app-automation/test-cases",
            "/app-automation/test-suites",
            "/app-automation/executions",
            "/app-automation/reports",
            "/app-automation/scheduled-tasks",
            "/app-automation/notification-logs",
        ],
    },
    {
        "title": "推荐落地流程",
        "subtitle": "给新团队的最短上手路径",
        "image": ss("home"),
        "points": [
            "第 1 步：先完成配置中心里的 AI、浏览器、设备和通知配置。",
            "第 2 步：建立项目、版本和基础数据资产（接口、元素、测试数据）。",
            "第 3 步：根据业务场景选择 AI 用例生成、API 测试、UI 自动化或 APP 自动化开始沉淀资产。",
            "第 4 步：先手工跑通关键链路，再把它们纳入套件、报告和定时任务。",
            "第 5 步：把稳定的自然语言任务、钱包登录流程和高频回归用例沉淀成模板长期复用。",
        ],
        "related_pages": ["/home"],
    },
]


def inches(value: float) -> int:
    return int(value * EMU_PER_INCH)


def get_theme_xml() -> bytes:
    with NamedTemporaryFile(suffix=".docx", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        document = Document()
        document.add_paragraph("theme")
        document.save(temp_path)
        with zipfile.ZipFile(temp_path) as archive:
            return archive.read("word/theme/theme1.xml")
    finally:
        if temp_path.exists():
            temp_path.unlink()


def image_dimensions(path: str) -> tuple[int, int]:
    with Image.open(path) as image:
        return image.size


def fit_image(
    path: str,
    max_width: int,
    max_height: int,
    x: int,
    y: int,
) -> tuple[int, int, int, int]:
    width, height = image_dimensions(path)
    scale = min(max_width / width, max_height / height)
    scaled_width = int(width * scale)
    scaled_height = int(height * scale)
    adjusted_x = x + (max_width - scaled_width) // 2
    adjusted_y = y + (max_height - scaled_height) // 2
    return adjusted_x, adjusted_y, scaled_width, scaled_height


def paragraph_xml(
    text: str,
    font_size: int,
    color: str,
    level: int = 0,
    bold: bool = False,
) -> str:
    bold_attr = ' b="1"' if bold else ""
    return f"""
    <a:p>
      <a:pPr lvl="{level}"/>
      <a:r>
        <a:rPr lang="zh-CN" sz="{font_size}" dirty="0"{bold_attr}>
          <a:solidFill><a:srgbClr val="{color}"/></a:solidFill>
          <a:latin typeface="Microsoft YaHei"/>
          <a:ea typeface="Microsoft YaHei"/>
          <a:cs typeface="Microsoft YaHei"/>
        </a:rPr>
        <a:t>{escape(text)}</a:t>
      </a:r>
      <a:endParaRPr lang="zh-CN" sz="{font_size}" dirty="0">
        <a:latin typeface="Microsoft YaHei"/>
        <a:ea typeface="Microsoft YaHei"/>
        <a:cs typeface="Microsoft YaHei"/>
      </a:endParaRPr>
    </a:p>""".strip()


def textbox_xml(
    shape_id: int,
    name: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    paragraphs: list[str],
) -> str:
    paragraphs_xml = "".join(paragraphs)
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{escape(name)}"/>
        <p:cNvSpPr txBox="1"/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm>
          <a:off x="{x}" y="{y}"/>
          <a:ext cx="{cx}" cy="{cy}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        <a:noFill/>
        <a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr wrap="square" rtlCol="0" anchor="t"/>
        <a:lstStyle/>
        {paragraphs_xml}
      </p:txBody>
    </p:sp>""".strip()


def badge_xml(
    shape_id: int,
    name: str,
    text: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
    fill: str = "E8EEF9",
) -> str:
    return f"""
    <p:sp>
      <p:nvSpPr>
        <p:cNvPr id="{shape_id}" name="{escape(name)}"/>
        <p:cNvSpPr txBox="0"/>
        <p:nvPr/>
      </p:nvSpPr>
      <p:spPr>
        <a:xfrm>
          <a:off x="{x}" y="{y}"/>
          <a:ext cx="{cx}" cy="{cy}"/>
        </a:xfrm>
        <a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>
        <a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>
        <a:ln><a:noFill/></a:ln>
      </p:spPr>
      <p:txBody>
        <a:bodyPr wrap="square" rtlCol="0" anchor="ctr"/>
        <a:lstStyle/>
        {paragraph_xml(text, 1600, "214067", bold=True)}
      </p:txBody>
    </p:sp>""".strip()


def picture_xml(
    shape_id: int,
    name: str,
    rel_id: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
) -> str:
    return f"""
    <p:pic>
      <p:nvPicPr>
        <p:cNvPr id="{shape_id}" name="{escape(name)}"/>
        <p:cNvPicPr>
          <a:picLocks noChangeAspect="1"/>
        </p:cNvPicPr>
        <p:nvPr/>
      </p:nvPicPr>
      <p:blipFill>
        <a:blip r:embed="{rel_id}"/>
        <a:stretch><a:fillRect/></a:stretch>
      </p:blipFill>
      <p:spPr>
        <a:xfrm>
          <a:off x="{x}" y="{y}"/>
          <a:ext cx="{cx}" cy="{cy}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:pic>""".strip()


def slide_xml(slide: dict[str, object], rel_id: str) -> str:
    image_path = str(slide["image"])
    title = str(slide["title"])
    subtitle = str(slide["subtitle"])
    points = [str(item) for item in slide["points"]]
    related_pages = [str(item) for item in slide.get("related_pages", [])]

    if slide.get("kind") == "cover":
        image_box = fit_image(
            image_path,
            inches(7.8),
            inches(4.4),
            inches(5.0),
            inches(1.7),
        )
        shapes = [
            textbox_xml(
                2,
                "Cover Title",
                inches(0.8),
                inches(1.2),
                inches(4.1),
                inches(1.6),
                [paragraph_xml(title, 2600, "1F2A44", bold=True)],
            ),
            textbox_xml(
                3,
                "Cover Subtitle",
                inches(0.9),
                inches(2.4),
                inches(3.9),
                inches(2.2),
                [
                    paragraph_xml(subtitle, 1280, "4A607C"),
                    paragraph_xml("版本基于本地部署环境整理，截图来源于 2026-04-20 当前实例。", 1080, "6B778C"),
                ],
            ),
            badge_xml(4, "Cover Badge", "TestHub 本地部署版", inches(0.9), inches(0.6), inches(2.2), inches(0.45), fill="D9E7FF"),
            picture_xml(5, "Cover Image", rel_id, *image_box),
        ]
    else:
        image_box = fit_image(
            image_path,
            inches(7.0),
            inches(4.8),
            inches(0.7),
            inches(1.5),
        )
        point_paragraphs = [paragraph_xml(item, 1140, "334155") for item in points]
        footer_lines = [
            paragraph_xml("页面入口：" + " / ".join(related_pages), 920, "6B7280"),
            paragraph_xml("说明：截图取自当前本地环境，实际按钮名称可能随版本微调。", 900, "94A3B8"),
        ]
        shapes = [
            textbox_xml(
                2,
                "Title",
                inches(0.7),
                inches(0.45),
                inches(8.2),
                inches(0.65),
                [paragraph_xml(title, 2050, "172554", bold=True)],
            ),
            badge_xml(
                3,
                "Badge",
                subtitle,
                inches(9.25),
                inches(0.45),
                inches(3.2),
                inches(0.48),
            ),
            picture_xml(4, "Screenshot", rel_id, *image_box),
            textbox_xml(
                5,
                "Body",
                inches(8.0),
                inches(1.45),
                inches(4.6),
                inches(4.9),
                point_paragraphs,
            ),
            textbox_xml(
                6,
                "Footer",
                inches(0.8),
                inches(6.5),
                inches(12.0),
                inches(0.4),
                footer_lines,
            ),
        ]

    shapes_xml = "".join(shapes)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
       xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
       xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:bg>
      <p:bgPr>
        <a:solidFill><a:srgbClr val="F7F9FC"/></a:solidFill>
        <a:effectLst/>
      </p:bgPr>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
      {shapes_xml}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>
"""


def build_slide_relationships(image_index: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="../media/image{image_index}.png"/>
</Relationships>
"""


SLIDE_LAYOUT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldLayout xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
             type="blank"
             preserve="1">
  <p:cSld name="Blank">
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sldLayout>
"""


SLIDE_LAYOUT_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="../slideMasters/slideMaster1.xml"/>
</Relationships>
"""


SLIDE_MASTER_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sldMaster xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld name="TestHub Master">
    <p:bg>
      <p:bgPr>
        <a:solidFill><a:schemeClr val="bg1"/></a:solidFill>
        <a:effectLst/>
      </p:bgPr>
    </p:bg>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>
  <p:sldLayoutIdLst>
    <p:sldLayoutId id="2147483649" r:id="rId1"/>
  </p:sldLayoutIdLst>
  <p:txStyles>
    <p:titleStyle/>
    <p:bodyStyle/>
    <p:otherStyle/>
  </p:txStyles>
</p:sldMaster>
"""


SLIDE_MASTER_RELS_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme" Target="../theme/theme1.xml"/>
</Relationships>
"""


def presentation_xml(slide_count: int) -> str:
    slide_ids = []
    for index in range(slide_count):
        slide_ids.append(f'    <p:sldId id="{256 + index}" r:id="rId{index + 2}"/>')
    slide_ids_xml = "\n".join(slide_ids)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldMasterIdLst>
    <p:sldMasterId id="2147483648" r:id="rId1"/>
  </p:sldMasterIdLst>
  <p:sldIdLst>
{slide_ids_xml}
  </p:sldIdLst>
  <p:sldSz cx="{SLIDE_CX}" cy="{SLIDE_CY}" type="screen16x9"/>
  <p:notesSz cx="6858000" cy="9144000"/>
  <p:defaultTextStyle/>
</p:presentation>
"""


def presentation_rels_xml(slide_count: int) -> str:
    relationships = [
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster" Target="slideMasters/slideMaster1.xml"/>'
    ]
    for index in range(slide_count):
        relationships.append(
            f'  <Relationship Id="rId{index + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index + 1}.xml"/>'
        )
    relationships.extend(
        [
            f'  <Relationship Id="rId{slide_count + 2}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps" Target="presProps.xml"/>',
            f'  <Relationship Id="rId{slide_count + 3}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps" Target="viewProps.xml"/>',
            f'  <Relationship Id="rId{slide_count + 4}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles" Target="tableStyles.xml"/>',
        ]
    )
    rels_xml = "\n".join(relationships)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{rels_xml}
</Relationships>
"""


def content_types_xml(slide_count: int) -> str:
    overrides = [
        '  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>',
        '  <Override PartName="/ppt/slideMasters/slideMaster1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml"/>',
        '  <Override PartName="/ppt/slideLayouts/slideLayout1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml"/>',
        '  <Override PartName="/ppt/theme/theme1.xml" ContentType="application/vnd.openxmlformats-officedocument.theme+xml"/>',
        '  <Override PartName="/ppt/presProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presProps+xml"/>',
        '  <Override PartName="/ppt/viewProps.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml"/>',
        '  <Override PartName="/ppt/tableStyles.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml"/>',
        '  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for index in range(slide_count):
        overrides.append(
            f'  <Override PartName="/ppt/slides/slide{index + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        )
    overrides_xml = "\n".join(overrides)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Default Extension="png" ContentType="image/png"/>
{overrides_xml}
</Types>
"""


def root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
"""


def app_xml(slide_count: int) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
            xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Codex</Application>
  <PresentationFormat>Widescreen</PresentationFormat>
  <Slides>{slide_count}</Slides>
  <Notes>0</Notes>
  <HiddenSlides>0</HiddenSlides>
  <MMClips>0</MMClips>
  <ScaleCrop>false</ScaleCrop>
  <HeadingPairs>
    <vt:vector size="2" baseType="variant">
      <vt:variant><vt:lpstr>幻灯片标题</vt:lpstr></vt:variant>
      <vt:variant><vt:i4>{slide_count}</vt:i4></vt:variant>
    </vt:vector>
  </HeadingPairs>
  <TitlesOfParts>
    <vt:vector size="{slide_count}" baseType="lpstr">
      {''.join(f'<vt:lpstr>{escape(str(slide["title"]))}</vt:lpstr>' for slide in SLIDES)}
    </vt:vector>
  </TitlesOfParts>
  <Company></Company>
  <LinksUpToDate>false</LinksUpToDate>
  <SharedDoc>false</SharedDoc>
  <HyperlinksChanged>false</HyperlinksChanged>
  <AppVersion>16.0000</AppVersion>
</Properties>
"""


def core_xml() -> str:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                   xmlns:dc="http://purl.org/dc/elements/1.1/"
                   xmlns:dcterms="http://purl.org/dc/terms/"
                   xmlns:dcmitype="http://purl.org/dc/dcmitype/"
                   xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>TestHub 功能使用教程</dc:title>
  <dc:subject>本地部署使用教程</dc:subject>
  <dc:creator>Codex</dc:creator>
  <cp:keywords>TestHub, 教程, 本地部署, PPT</cp:keywords>
  <dc:description>覆盖 TestHub 主要功能模块的图文教程</dc:description>
  <cp:lastModifiedBy>Codex</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>
"""


def pres_props_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentationPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
                  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
                  xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"/>
"""


def view_props_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:viewPr xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
          xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:normalViewPr>
    <p:restoredLeft sz="15620"/>
    <p:restoredTop sz="94660"/>
  </p:normalViewPr>
  <p:slideViewPr>
    <p:cSldViewPr snapToGrid="1" snapToObjects="1" showGuides="1">
      <p:commonViewPr>
        <p:scale sx="100" sy="100"/>
        <p:origin x="0" y="0"/>
      </p:commonViewPr>
    </p:cSldViewPr>
  </p:slideViewPr>
  <p:notesTextViewPr>
    <p:cViewPr varScale="1">
      <p:scale sx="100" sy="100"/>
      <p:origin x="0" y="0"/>
    </p:cViewPr>
  </p:notesTextViewPr>
  <p:gridSpacing cx="780288" cy="780288"/>
</p:viewPr>
"""


def table_styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<a:tblStyleLst xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>
"""


def markdown_image_path(image_path: str) -> str:
    relative = os.path.relpath(Path(image_path).resolve(), DOCS_DIR.resolve())
    return Path(relative).as_posix()


def build_markdown() -> str:
    lines = [
        "# TestHub 功能使用教程",
        "",
        "本文档基于本地部署环境整理，覆盖当前项目里可见的主要功能模块、典型使用路径和钱包登录实战流程。",
        "",
        "## 使用前准备",
        "",
        "1. 打开前端：[http://localhost:3000](http://localhost:3000)",
        "2. 确认后端接口可用：[http://127.0.0.1:8000/api/users/login/](http://127.0.0.1:8000/api/users/login/)",
        "3. 演示登录请使用本地环境里已配置的管理员账号",
        "4. 如需体验钱包登录，请先在本机 Chrome 中安装并登录 MetaMask。",
        "",
        "---",
        "",
    ]

    for index, slide in enumerate(SLIDES[1:], start=1):
        title = str(slide["title"])
        subtitle = str(slide["subtitle"])
        image = markdown_image_path(str(slide["image"]))
        points = [str(item) for item in slide["points"]]
        related_pages = [str(item) for item in slide.get("related_pages", [])]

        lines.extend(
            [
                f"## {index}. {title}",
                "",
                f"**功能定位：** {subtitle}",
                "",
                f"![{title}]({image})",
                "",
                "**推荐入口：**",
                "",
            ]
        )
        for page in related_pages:
            lines.append(f"- `{page}`")
        lines.extend(["", "**使用说明：**", ""])
        for point in points:
            lines.append(f"1. {point}")
        lines.extend(["", "---", ""])

    return "\n".join(lines).strip() + "\n"


def build_pptx() -> None:
    theme_xml = get_theme_xml()
    slide_count = len(SLIDES)

    PPTX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(PPTX_PATH, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml(slide_count))
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("docProps/app.xml", app_xml(slide_count))
        archive.writestr("docProps/core.xml", core_xml())
        archive.writestr("ppt/presentation.xml", presentation_xml(slide_count))
        archive.writestr("ppt/_rels/presentation.xml.rels", presentation_rels_xml(slide_count))
        archive.writestr("ppt/presProps.xml", pres_props_xml())
        archive.writestr("ppt/viewProps.xml", view_props_xml())
        archive.writestr("ppt/tableStyles.xml", table_styles_xml())
        archive.writestr("ppt/theme/theme1.xml", theme_xml)
        archive.writestr("ppt/slideLayouts/slideLayout1.xml", SLIDE_LAYOUT_XML)
        archive.writestr("ppt/slideLayouts/_rels/slideLayout1.xml.rels", SLIDE_LAYOUT_RELS_XML)
        archive.writestr("ppt/slideMasters/slideMaster1.xml", SLIDE_MASTER_XML)
        archive.writestr("ppt/slideMasters/_rels/slideMaster1.xml.rels", SLIDE_MASTER_RELS_XML)

        for index, slide in enumerate(SLIDES, start=1):
            archive.writestr(f"ppt/slides/slide{index}.xml", slide_xml(slide, "rId2"))
            archive.writestr(
                f"ppt/slides/_rels/slide{index}.xml.rels",
                build_slide_relationships(index),
            )
            image_path = Path(str(slide["image"]))
            archive.writestr(f"ppt/media/image{index}.png", image_path.read_bytes())


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    MARKDOWN_PATH.write_text(build_markdown(), encoding="utf-8")
    build_pptx()
    print(f"Markdown written to: {MARKDOWN_PATH}")
    print(f"PPTX written to: {PPTX_PATH}")
    print(f"Slides generated: {len(SLIDES)}")


if __name__ == "__main__":
    main()
