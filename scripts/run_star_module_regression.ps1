$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    Write-Host "[1/3] Starting local MySQL runtime..."
    & "$PSScriptRoot\start_local_mysql.ps1"

    Write-Host "[2/3] Running Star module regression tests..."
    .\.venv312\Scripts\python.exe manage.py test `
        backend.tests.test_star_module_boundaries `
        backend.tests.test_unified_projects `
        backend.tests.test_unified_scheduler `
        backend.tests.test_ai_testing_module `
        backend.tests.test_knowledge_base_embeddings `
        backend.tests.test_ocr_service_batches -v 2
    if ($LASTEXITCODE -ne 0) {
        throw "Star module regression tests failed (exit=$LASTEXITCODE)."
    }

    Write-Host "[3/3] Star module regression tests passed."
} finally {
    try {
        & "$PSScriptRoot\stop_local_mysql.ps1" | Out-Null
    } catch {
        Write-Warning "Failed to stop local MySQL automatically: $($_.Exception.Message)"
    }
    Pop-Location
}
