# Git Hooks

本目录由 [husky](https://typicode.github.io/husky/) 管理，仓库根 `package.json` 仅持有 husky 依赖。

## 安装

第一次 clone 后，在仓库根执行：

```bash
npm install
```

`prepare` 脚本会自动配置 `core.hooksPath = .husky`。

## pre-commit 行为

`.husky/pre-commit` 进入 `frontend/` 调用 `npx --no-install lint-staged`，按 `frontend/package.json#lint-staged` 配置对暂存的 JS/Vue/JSON/Markdown 文件做格式化与 ESLint 修复。

如果 `frontend/node_modules` 不存在（例如纯后端开发者从未 `npm install`），hook 会自动跳过，避免阻塞提交。

## 后端 Python 检查

`pre-commit` 会对暂存的 `.py` 文件依次执行：

1. `ruff check --fix` — Lint + 自动可修复项
2. `black --quiet` — 格式化

修改后的文件会自动 `git add` 进暂存区。如果工具未安装（未跑过 `pip install -r requirements-dev.txt`），相应步骤会跳过，hook 不阻塞提交。

migrations/ 目录不在检查范围内。
