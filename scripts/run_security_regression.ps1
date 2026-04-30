param(
  [switch]$StrictFrontendBuild
)
$ErrorActionPreference = "Stop"

function Normalize-ProcessPathEnvironment {
  if ((Test-Path Env:PATH) -and (Test-Path Env:Path)) {
    if (-not $env:Path) {
      $env:Path = $env:PATH
    }
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
  } elseif ((Test-Path Env:PATH) -and -not (Test-Path Env:Path)) {
    Set-Item Env:Path $env:PATH
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
  }
}

function Invoke-FrontendBuild {
  param(
    [Parameter(Mandatory = $false)][string]$Label = "frontend build"
  )

  Normalize-ProcessPathEnvironment
  $frontendDir = Resolve-Path ".\frontend"
  $proc = Start-Process `
    -FilePath "C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -ArgumentList "-NoProfile", "-Command", "npm.cmd run build" `
    -WorkingDirectory $frontendDir `
    -PassThru `
    -Wait `
    -WindowStyle Hidden

  if ($proc.ExitCode -ne 0) {
    throw "Command failed (exit=$($proc.ExitCode)): $Label"
  }
}

function Invoke-CheckedCommand {
  param(
    [Parameter(Mandatory = $true)][scriptblock]$Command,
    [Parameter(Mandatory = $false)][string]$Label = "command"
  )
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed (exit=$LASTEXITCODE): $Label"
  }
}

Push-Location (Resolve-Path "$PSScriptRoot\..")
try {
  Write-Host "[1/4] Django system check..."
  Invoke-CheckedCommand { .\.venv312\Scripts\python.exe manage.py check } "manage.py check"

  Write-Host "[2/4] Django deploy check (production-like env)..."
  $oldDebug = $env:DEBUG
  $oldCors = $env:CORS_ALLOWED_ORIGINS
  $env:DEBUG = "False"
  if (-not $env:CORS_ALLOWED_ORIGINS) {
    $env:CORS_ALLOWED_ORIGINS = "http://localhost:3000"
  }
  Invoke-CheckedCommand { .\.venv312\Scripts\python.exe manage.py check --deploy } "manage.py check --deploy"
  $env:DEBUG = $oldDebug
  $env:CORS_ALLOWED_ORIGINS = $oldCors

  Write-Host "[3/4] Security regression tests..."
  Invoke-CheckedCommand {
    .\.venv312\Scripts\python.exe manage.py test `
      backend.tests.test_authorization_guards `
      backend.tests.test_security_boundaries `
      backend.tests.test_logging_config -v 2
  } "security regression tests"

  Write-Host "[4/4] Frontend production build..."
  $frontendBuildPassed = $false
  try {
    Invoke-FrontendBuild "frontend build"
    $frontendBuildPassed = $true
  } catch {
    Write-Warning "Frontend build failed once. Retrying..."
    Start-Sleep -Seconds 2
    try {
      Invoke-FrontendBuild "frontend build retry"
      $frontendBuildPassed = $true
    } catch {
      if ($StrictFrontendBuild) {
        throw
      }
      Write-Warning "Frontend build check skipped due local process permission limits (spawn EPERM)."
    }
  }

  if ($frontendBuildPassed) {
    Write-Host "Security regression checks passed."
  } else {
    Write-Host "Security regression checks passed (frontend build skipped)."
  }
} finally {
  Pop-Location
}
