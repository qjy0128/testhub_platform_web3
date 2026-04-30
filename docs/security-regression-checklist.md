# Security Regression Checklist

This checklist targets the high-risk boundaries fixed in this branch.

## 1) Automated Checks

Run these first:

```powershell
.\.venv312\Scripts\python.exe manage.py check
```

```powershell
$env:DEBUG='False'
$env:CORS_ALLOWED_ORIGINS='http://localhost:3000'
.\.venv312\Scripts\python.exe manage.py check --deploy
```

```powershell
.\.venv312\Scripts\python.exe manage.py test `
  backend.tests.test_authorization_guards `
  backend.tests.test_security_boundaries `
  backend.tests.test_logging_config -v 2
```

```powershell
cd frontend
npm.cmd run build
```

## 2) Manual Access Control Verification

Use user A and user B (different project scopes):

1. APP Automation:
- user B cannot list/update/delete user A's test cases/suites/scheduled tasks.
- user B cannot bind user A's test case into their own suite.
- user B cannot run a scheduled task referencing user A's project resources.

2. Requirement Analysis generation tasks:
- user B cannot fetch `/generation-tasks/{task_id}` for user A when not same accessible project.
- user B cannot open SSE `/generation-tasks/{task_id}/stream_progress/` for user A's task.

3. Assistant UI rendering:
- submit payload containing `<script>alert(1)</script>` and verify it renders as text, not executable HTML.

## 3) File Path Boundary Verification

For APP element image upload + preview + delete:

1. Upload with path traversal-like values (e.g. `../x.png`, absolute path, non-image extension).
2. Confirm API rejects invalid category/filename/path.
3. Confirm valid uploads stay under `apps/app_automation/Template/`.

## 4) Release Gate

Before release:

1. `check --deploy` must be clean under production-like env.
2. Security test suite must pass.
3. Frontend production build must pass.
