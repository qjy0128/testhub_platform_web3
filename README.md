# TestHub Web3 — DApp 自动化测试平台

<div align="center">

**在 TestHub 测试管理平台基础上，扩展的 EVM DApp + MetaMask 钱包自动化测试分支**

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-4.2-green.svg)](https://www.djangoproject.com/)
[![Vue](https://img.shields.io/badge/Vue-3.3-brightgreen.svg)](https://vuejs.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

</div>

## 这个仓库是什么

这是 [TestHub 智能测试平台](https://github.com/chenjigang4167/testhub_platform) 的一个 Web3 分支，主线在 **EVM DApp 自动化测试**，第一期提供基于 MetaMask 的钱包动作编排能力。TestHub 本身的测试用例管理、API 测试、UI 自动化、AI 需求分析、数据工厂等能力均保留。

## Web3 能力（本分支新增）

AI UI 自动化任务中可开启**钱包模式**，由平台接管用户本机真实 Chrome Profile（带 MetaMask 扩展），以确定性方式处理钱包弹窗。

### 第一期支持的钱包动作

| 动作 | 说明 | 幂等规则 |
|------|------|----------|
| **连接钱包** | dApp 发起 Connect 流程，平台自动选择 MetaMask 并授权 | 已连接则直接成功 |
| **切链** | 响应 dApp 切链请求，包括 `wallet_addEthereumChain` 触发的先加链再切链流程 | 当前链已匹配则直接成功 |
| **签名消息** | 捕获签名弹窗并点击确认，返回 dApp 校验签名结果 | — |
| **确认交易** | 捕获交易确认弹窗，等待按钮稳定后点击发送 | — |

### 技术方案

分为 3 层：

1. **受控 Chrome 会话层** (`apps/ui_automation/wallet_session.py`)
   校验 Chrome 可执行文件、user_data_dir、profile_directory，按配置关闭现有 Chrome 进程，以远程调试模式重启 Chrome，校验 MetaMask 扩展存在，自动化运行时通过 CDP 接入该会话。

2. **钱包适配层** (`apps/ui_automation/ai_base.py` 中的 MetaMask 适配器)
   识别 MetaMask 弹窗场景，执行确定性动作，返回结构化结果和详细日志。接口预留可扩展性，后续可接入 OKX / Phantom 等钱包适配器。

3. **AI/UI 自动化执行层**（既有）
   负责 dApp 页面导航、点击、断言、截图。识别到钱包步骤时临时切换到钱包适配层，完成后再切回 dApp 页面。

### 范围与边界

**支持：** Windows 本地部署 · Google Chrome · 用户自己的 Chrome Profile · MetaMask · EVM 链 · 有头执行

**暂不支持：** Firefox / Edge / WebKit · Phantom / Backpack / OKX 等其它钱包 · 钱包创建 / 导入 / 助记词管理 · CI 或远程浏览器环境 · 非 EVM 链（Solana 等） · 无头执行

### 配置项

在 AI 模式配置中心 (`/configuration/ai-mode`) 启用钱包模式并填入以下字段：

- `enabled` — 是否启用
- `chrome_executable_path` — Chrome 可执行文件路径
- `user_data_dir` — Chrome 用户数据目录
- `profile_directory` — 默认 `Default`
- `remote_debugging_port` — 远程调试端口
- `force_close_existing_chrome` — 默认 `false`（会强杀所有 Chrome 进程，仅建议在专用测试机启用）
- `metamask_extension_id` — 支持自动探测与手工覆盖

## 快速开始

### 环境要求

- Python 3.12（其他版本可能兼容性问题）
- Node.js 18+（仅开发/构建前端）
- MySQL 8.0+
- Chrome 浏览器 + MetaMask 扩展（使用钱包模式时必需）
- Redis 6.0+（可选，APP 自动化相关）
- Java 17+（可选，Allure 报告生成）

### 后端

```bash
# 1. 克隆
git clone https://github.com/qjy0128/testhub_platform_web3.git
cd testhub_platform_web3

# 2. 虚拟环境（推荐 Python 3.12；3.13/3.14 部分依赖暂不兼容）
py -3.12 -m venv .venv          # Windows
# python3.12 -m venv .venv      # macOS / Linux

# 激活
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

# 3. 依赖
pip install -r requirements.txt
# 开发期工具（black/ruff/pytest-django）：
# pip install -r requirements-dev.txt

# 4. 配置
cp .env.example .env
# 编辑 .env 填入数据库连接、SECRET_KEY 等

# 5. 数据库
mysql -u root -p -e "CREATE DATABASE testhub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
python manage.py migrate
python manage.py createsuperuser

# 6. UI 自动化初始化
python manage.py init_locator_strategies

# 7. 启动
python manage.py runserver
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认运行在 `http://localhost:5173`，后端 `http://localhost:8000`。API 文档：`/api/docs/`（Swagger）。

### 钱包模式准备

1. 在 Chrome 里用你的测试钱包准备好 Profile，安装 MetaMask 扩展并登录一次
2. 在 TestHub 管理后台 `/configuration/ai-mode` 配置钱包浏览器路径
3. 在 AI UI 自动化任务中勾选"钱包模式"即可

> ⚠️ **强烈建议：** 钱包模式下**只使用专门的测试钱包**，仅持有 testnet 代币或极少量主网资金。不要用日常钱包的 Chrome Profile 直接跑自动化。

## 底层能力（继承自 TestHub）

<details>
<summary>展开查看完整功能列表</summary>

### 🤖 AI 能力
- AI 需求分析（PDF / Word / TXT 解析，自动生成测试用例）
- 多模型支持（DeepSeek、通义千问、硅基流动、OpenAI 兼容）
- 基于 browser-use 的 AI 浏览器自动化（文本模式 + 视觉模式）
- Dify 智能助手集成

### 📋 测试管理
- 测试用例生命周期管理（创建、编辑、版本、归档、步骤、附件、评论）
- 用例评审流程（多人评审、评审模板、检查清单）
- 测试计划与执行（手动 + 自动化，执行历史对比）
- 多维度报告与 Allure 集成

### 🌐 API 测试
- HTTP / WebSocket、多环境变量、测试套件、断言、定时任务、Allure 报告

### 🖥️ UI 自动化
- Selenium / Playwright 双引擎
- 元素库管理、POM 模式、脚本录制回放
- 多浏览器、执行日志 / 截图 / 视频
- Cron 定时任务

### 📱 APP 自动化（Android）
- 基于 Airtest 的图像识别测试
- 设备池管理、ADB 集成、多分辨率适配
- 组件化编排、JSON UI Flow、变量作用域
- Celery 异步执行 + pytest + Allure

### 🏭 数据工厂
- 字符 / 编码 / 随机 / 加密 / JSON / Crontab / 测试数据生成共 50+ 工具
- 标签系统 + 在 API / UI 测试中引用

### 👥 项目与权限
- 多项目、成员角色、版本管理、个性化设置

</details>

## 项目结构

```
testhub_platform/
├── apps/
│   ├── ui_automation/              # UI 自动化（本仓库的 web3 扩展点）
│   │   ├── wallet_session.py       # 🆕 受控 Chrome 会话层
│   │   ├── ai_base.py              # 🆕 MetaMask 适配器
│   │   ├── ai_agent.py             # AI 执行核心
│   │   └── migrations/             # 🆕 wallet_automation 系列迁移
│   ├── api_testing/                # API 测试
│   ├── app_automation/             # APP 自动化
│   ├── testcases/ testsuites/ ...  # 测试管理
│   └── requirement_analysis/       # AI 需求分析
├── backend/                        # Django 项目配置
├── frontend/                       # Vue 3 前端
├── docs/
│   └── superpowers/
│       ├── specs/2026-04-17-metamask-wallet-automation-design.md
│       └── plans/2026-04-17-metamask-wallet-automation.md
└── requirements.txt
```

## 安全注意事项

这个仓库涉及钱包自动化，**请务必**遵守以下原则：

- ❌ **不要**把真实资金钱包的 Chrome Profile 提交到任何仓库
- ❌ **不要**把 `.tmp/`、运行时生成的 profile 副本、截图、日志提交到仓库（本项目 `.gitignore` 已覆盖）
- ❌ **不要**把 `.env` 中的真实密钥、SECRET_KEY 提交
- ✅ 钱包模式**只用测试钱包**（仅含 testnet 资产）
- ✅ MetaMask 解锁密码使用强密码
- ✅ 若曾意外提交过钱包数据 —— 换助记词、重建仓库、轮换 SECRET_KEY

## 路线图（后续迭代）

- 多钱包支持：OKX Wallet、Phantom、Backpack
- 非 EVM 链：Solana、TON
- 无头 / CI 执行支持
- Firefox / Edge 支持

## 致谢

本项目 fork 自 [chenjigang4167/testhub_platform](https://github.com/chenjigang4167/testhub_platform)，在其基础上扩展 Web3 能力。底层测试管理、API 测试、UI 自动化、AI 需求分析等功能版权归原作者所有。

## 许可证

MIT License，与上游保持一致。
