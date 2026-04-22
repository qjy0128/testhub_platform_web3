from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


BASE_FRONTEND_URL = "http://127.0.0.1:3000"
BASE_BACKEND_URL = "http://127.0.0.1:8000"
TUTORIAL_USERNAME_ENV = "TESTHUB_TUTORIAL_USERNAME"
TUTORIAL_PASSWORD_ENV = "TESTHUB_TUTORIAL_PASSWORD"
CHROME_PATHS = [
    Path(r"C:\Users\qjy01\AppData\Local\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
]
OUTPUT_ROOT = Path(r"D:\TestHub\testhub_platform\docs\tutorial_assets")
SCREENSHOT_DIR = OUTPUT_ROOT / "screenshots"
ROUTE_MANIFEST_PATH = OUTPUT_ROOT / "route_manifest.json"


ROUTES = [
    {"slug": "login", "path": "/login", "title": "登录页", "auth": False, "wait_ms": 2500},
    {"slug": "home", "path": "/home", "title": "首页总览", "auth": True},
    {"slug": "ai_requirement_analysis", "path": "/ai-generation/requirement-analysis", "title": "AI需求分析", "auth": True},
    {"slug": "ai_generated_testcases", "path": "/ai-generation/generated-testcases", "title": "AI生成测试用例", "auth": True},
    {"slug": "ai_projects", "path": "/ai-generation/projects", "title": "项目管理", "auth": True},
    {"slug": "ai_testcases", "path": "/ai-generation/testcases", "title": "测试用例管理", "auth": True},
    {"slug": "ai_versions", "path": "/ai-generation/versions", "title": "版本管理", "auth": True},
    {"slug": "ai_reviews", "path": "/ai-generation/reviews", "title": "用例评审列表", "auth": True},
    {"slug": "ai_review_templates", "path": "/ai-generation/review-templates", "title": "评审模板", "auth": True},
    {"slug": "ai_executions", "path": "/ai-generation/executions", "title": "测试计划与执行", "auth": True},
    {"slug": "ai_reports", "path": "/ai-generation/reports", "title": "AI测试报告", "auth": True},
    {"slug": "api_dashboard", "path": "/api-testing/dashboard", "title": "API测试仪表盘", "auth": True},
    {"slug": "api_projects", "path": "/api-testing/projects", "title": "API项目管理", "auth": True},
    {"slug": "api_interfaces", "path": "/api-testing/interfaces", "title": "接口管理", "auth": True},
    {"slug": "api_automation", "path": "/api-testing/automation", "title": "API自动化测试", "auth": True},
    {"slug": "api_history", "path": "/api-testing/history", "title": "请求历史", "auth": True},
    {"slug": "api_environments", "path": "/api-testing/environments", "title": "环境管理", "auth": True},
    {"slug": "api_reports", "path": "/api-testing/reports", "title": "API测试报告", "auth": True},
    {"slug": "api_scheduled_tasks", "path": "/api-testing/scheduled-tasks", "title": "API定时任务", "auth": True},
    {"slug": "api_notification_logs", "path": "/api-testing/notification-logs", "title": "API通知日志", "auth": True},
    {"slug": "ui_dashboard", "path": "/ui-automation/dashboard", "title": "UI自动化仪表盘", "auth": True},
    {"slug": "ui_projects", "path": "/ui-automation/projects", "title": "UI项目管理", "auth": True},
    {"slug": "ui_elements", "path": "/ui-automation/elements-enhanced", "title": "UI元素管理", "auth": True},
    {"slug": "ui_test_cases", "path": "/ui-automation/test-cases", "title": "UI测试用例", "auth": True},
    {"slug": "ui_scripts_enhanced", "path": "/ui-automation/scripts-enhanced", "title": "UI脚本编排", "auth": True},
    {"slug": "ui_scripts", "path": "/ui-automation/scripts", "title": "UI脚本列表", "auth": True},
    {"slug": "ui_suites", "path": "/ui-automation/suites", "title": "UI测试套件", "auth": True},
    {"slug": "ui_executions", "path": "/ui-automation/executions", "title": "UI执行记录", "auth": True},
    {"slug": "ui_reports", "path": "/ui-automation/reports", "title": "UI测试报告", "auth": True},
    {"slug": "ui_scheduled_tasks", "path": "/ui-automation/scheduled-tasks", "title": "UI定时任务", "auth": True},
    {"slug": "ui_notification_logs", "path": "/ui-automation/notification-logs", "title": "UI通知日志", "auth": True},
    {"slug": "ai_mode_testing", "path": "/ai-intelligent-mode/testing", "title": "AI智能测试", "auth": True},
    {"slug": "ai_mode_cases", "path": "/ai-intelligent-mode/cases", "title": "AI智能用例管理", "auth": True},
    {"slug": "ai_mode_execution_records", "path": "/ai-intelligent-mode/execution-records", "title": "AI智能执行记录", "auth": True},
    {"slug": "data_factory", "path": "/data-factory", "title": "数据工厂", "auth": True},
    {"slug": "config_ai_model", "path": "/configuration/ai-model", "title": "AI模型配置", "auth": True},
    {"slug": "config_prompt", "path": "/configuration/prompt-config", "title": "提示词配置", "auth": True},
    {"slug": "config_generation", "path": "/configuration/generation-config", "title": "生成策略配置", "auth": True},
    {"slug": "config_ui_env", "path": "/configuration/ui-env", "title": "UI环境配置", "auth": True},
    {"slug": "config_app_env", "path": "/configuration/app-env", "title": "APP环境配置", "auth": True},
    {"slug": "config_ai_mode", "path": "/configuration/ai-mode", "title": "AI智能模式配置", "auth": True},
    {"slug": "config_scheduled_task", "path": "/configuration/scheduled-task", "title": "通知与任务配置", "auth": True},
    {"slug": "config_dify", "path": "/configuration/dify", "title": "Dify配置", "auth": True},
    {"slug": "app_dashboard", "path": "/app-automation/dashboard", "title": "APP自动化仪表盘", "auth": True},
    {"slug": "app_projects", "path": "/app-automation/projects", "title": "APP项目管理", "auth": True},
    {"slug": "app_devices", "path": "/app-automation/devices", "title": "设备管理", "auth": True},
    {"slug": "app_packages", "path": "/app-automation/packages", "title": "应用包管理", "auth": True},
    {"slug": "app_elements", "path": "/app-automation/elements", "title": "APP元素管理", "auth": True},
    {"slug": "app_scene_builder", "path": "/app-automation/scene-builder", "title": "场景编排", "auth": True, "wait_ms": 5000},
    {"slug": "app_test_cases", "path": "/app-automation/test-cases", "title": "APP测试用例", "auth": True},
    {"slug": "app_test_suites", "path": "/app-automation/test-suites", "title": "APP测试套件", "auth": True},
    {"slug": "app_executions", "path": "/app-automation/executions", "title": "APP执行记录", "auth": True},
    {"slug": "app_reports", "path": "/app-automation/reports", "title": "APP测试报告", "auth": True},
    {"slug": "app_scheduled_tasks", "path": "/app-automation/scheduled-tasks", "title": "APP定时任务", "auth": True},
]


def resolve_browser_path() -> Path:
    for path in CHROME_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError("No supported local Chrome/Edge executable was found.")


def fetch_login_payload() -> dict[str, Any]:
    username = os.getenv(TUTORIAL_USERNAME_ENV, "").strip()
    password = os.getenv(TUTORIAL_PASSWORD_ENV, "").strip()
    if not username or not password:
        raise RuntimeError(
            f"Missing tutorial credentials. Set {TUTORIAL_USERNAME_ENV} and {TUTORIAL_PASSWORD_ENV} before running."
        )

    response = requests.post(
        f"{BASE_BACKEND_URL}/api/users/login/",
        json={"username": username, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def build_storage_init_script(payload: dict[str, Any]) -> str:
    user_json = json.dumps(payload["user"], ensure_ascii=False)
    return f"""
localStorage.setItem("access_token", {json.dumps(payload["access"])});
localStorage.setItem("refresh_token", {json.dumps(payload["refresh"])});
localStorage.setItem("user", {json.dumps(user_json)});
localStorage.setItem("token_expires_at", String(Date.now() + 30 * 60 * 1000));
"""


def remove_noise(page) -> None:
    page.evaluate(
        """
        () => {
          document.querySelectorAll('.el-message, .el-notification, .v-modal').forEach(el => el.remove());
        }
        """
    )


def extract_page_summary(page) -> dict[str, Any]:
    headings = page.locator("h1, h2, h3").evaluate_all(
        """
        els => els
          .map(el => (el.innerText || '').trim())
          .filter(Boolean)
          .slice(0, 6)
        """
    )
    buttons = page.locator("button, [role='button']").evaluate_all(
        """
        els => els
          .filter(el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length))
          .map(el => (el.innerText || el.getAttribute('aria-label') || '').trim())
          .filter(Boolean)
          .slice(0, 12)
        """
    )
    body_preview = page.locator("body").inner_text()[:600]
    return {
        "headings": headings,
        "buttons": buttons,
        "body_preview": body_preview,
    }


def capture_page(page, route: dict[str, Any]) -> dict[str, Any]:
    wait_ms = int(route.get("wait_ms", 3500))
    screenshot_path = SCREENSHOT_DIR / f"{route['slug']}.png"
    target_url = f"{BASE_FRONTEND_URL}{route['path']}"

    page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(wait_ms)
    remove_noise(page)

    summary = extract_page_summary(page)
    page.screenshot(path=str(screenshot_path), full_page=True)

    return {
        "slug": route["slug"],
        "title": route["title"],
        "path": route["path"],
        "url": page.url,
        "screenshot": str(screenshot_path),
        "headings": summary["headings"],
        "buttons": summary["buttons"],
        "body_preview": summary["body_preview"],
        "status": "ok",
    }


def main() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    browser_path = resolve_browser_path()
    login_payload = fetch_login_payload()
    storage_init_script = build_storage_init_script(login_payload)

    manifest: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(browser_path),
            headless=True,
            args=["--headless=new"],
        )

        public_context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")
        private_context = browser.new_context(viewport={"width": 1600, "height": 1000}, locale="zh-CN")
        private_context.add_init_script(storage_init_script)

        public_page = public_context.new_page()
        private_page = private_context.new_page()

        for route in ROUTES:
            page = private_page if route["auth"] else public_page
            try:
                item = capture_page(page, route)
            except PlaywrightTimeoutError as exc:
                item = {
                    "slug": route["slug"],
                    "title": route["title"],
                    "path": route["path"],
                    "status": "timeout",
                    "error": str(exc),
                }
            except Exception as exc:
                item = {
                    "slug": route["slug"],
                    "title": route["title"],
                    "path": route["path"],
                    "status": "error",
                    "error": repr(exc),
                }
            manifest.append(item)
            print(f"{route['slug']}: {item['status']}")

        public_context.close()
        private_context.close()
        browser.close()

    ROUTE_MANIFEST_PATH.write_text(
        json.dumps(
            {
                "base_frontend_url": BASE_FRONTEND_URL,
                "base_backend_url": BASE_BACKEND_URL,
                "browser_path": str(browser_path),
                "routes": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Wrote manifest to {ROUTE_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
