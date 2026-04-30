# Local Runtime Layout

All local-only runtime and test artifacts are stored under `testhub_platform/.local/`.

- MySQL data: `testhub_platform/.local/runtime/mysql-data`
- MySQL logs: `testhub_platform/.local/runtime/mysql-logs`
- Temp runtime cache: `testhub_platform/.local/runtime/tmp`
- Pytest cache: `testhub_platform/.local/runtime/pytest_cache`
- Probe output: `testhub_platform/.local/probes`
- Misc local files: `testhub_platform/.local/misc`

MySQL helper scripts:

```powershell
.\scripts\start_local_mysql.ps1
.\scripts\stop_local_mysql.ps1
```

Compatibility directories kept at the repo root:

- `logs/`
  Active application logs still live here because the Django settings and app automation executor write to `logs/app.log`, `logs/error.log`, and `logs/app_automation/...`.
- `.tmp`
  Repo-root compatibility entry that points at `.local/runtime/tmp`.
- `.pytest_cache`
  Repo-root compatibility entry that points at `.local/runtime/pytest_cache`.

Suggested `logs/` layout:

- `logs/app.log`
- `logs/error.log`
- `logs/app_automation/`
- `logs/runtime/`
- `logs/debug/`
- `logs/regression/`

The `.local/` directory is git-ignored and should never be committed.
