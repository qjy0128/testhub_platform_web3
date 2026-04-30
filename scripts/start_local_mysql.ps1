$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $repoRoot ".local\runtime"
$dataDir = Join-Path $runtimeRoot "mysql-data"
$logDir = Join-Path $runtimeRoot "mysql-logs"
$mysqlRoot = "C:\Program Files\MySQL\MySQL Server 8.4"
$mysqlBin = Join-Path $mysqlRoot "bin"
$mysqlAdmin = Join-Path $mysqlBin "mysqladmin.exe"
$mysqld = Join-Path $mysqlBin "mysqld.exe"
$stdoutLog = Join-Path $logDir "mysqld.out.log"
$stderrLog = Join-Path $logDir "mysqld.err.log"
$initOutLog = Join-Path $logDir "mysqld.init.out.log"
$initErrLog = Join-Path $logDir "mysqld.init.err.log"

New-Item -ItemType Directory -Force -Path $runtimeRoot, $dataDir, $logDir | Out-Null

function Normalize-ProcessPathEnvironment {
    # In some PowerShell hosts both PATH and Path exist, Start-Process fails on duplicate keys.
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

Normalize-ProcessPathEnvironment

if (-not (Test-Path $mysqlAdmin) -or -not (Test-Path $mysqld)) {
    throw "MySQL binaries not found under $mysqlBin. Install MySQL Server 8.x or adjust scripts/start_local_mysql.ps1."
}

function Initialize-MysqlDataDir {
    $mysqlSystemDir = Join-Path $dataDir "mysql"
    if (Test-Path $mysqlSystemDir) {
        return
    }

    Write-Output "Initializing local MySQL data directory..."
    $initProc = Start-Process -FilePath $mysqld `
        -ArgumentList "--no-defaults", "--initialize-insecure", "--basedir=`"$mysqlRoot`"", "--datadir=`"$dataDir`"" `
        -RedirectStandardOutput $initOutLog `
        -RedirectStandardError $initErrLog `
        -PassThru `
        -Wait `
        -WindowStyle Hidden

    if ($initProc.ExitCode -ne 0) {
        throw "MySQL data dir initialization failed (exit=$($initProc.ExitCode)). Check $initErrLog"
    }
}

function Test-MysqlAlive {
    $outFile = Join-Path $env:TEMP "testhub-mysqladmin-ping.out.log"
    $errFile = Join-Path $env:TEMP "testhub-mysqladmin-ping.err.log"
    $proc = Start-Process -FilePath $mysqlAdmin `
        -ArgumentList "-h", "127.0.0.1", "-P", "3306", "-u", "root", "ping" `
        -RedirectStandardOutput $outFile `
        -RedirectStandardError $errFile `
        -PassThru `
        -Wait `
        -WindowStyle Hidden
    return ($proc.ExitCode -eq 0)
}

if (Test-MysqlAlive) {
    Write-Output "MySQL already running on 127.0.0.1:3306"
    exit 0
}

Initialize-MysqlDataDir

$arguments = @(
    "--no-defaults",
    "--basedir=`"$mysqlRoot`"",
    "--datadir=`"$dataDir`"",
    "--port=3306",
    "--bind-address=127.0.0.1",
    "--plugin-dir=`"$(Join-Path $mysqlRoot 'lib\plugin')`"",
    "--lc-messages-dir=`"$(Join-Path $mysqlRoot 'share')`"",
    "--console"
)

$serverProc = Start-Process -FilePath $mysqld `
    -ArgumentList $arguments `
    -RedirectStandardOutput $stdoutLog `
    -RedirectStandardError $stderrLog `
    -PassThru `
    -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(25)
while ((Get-Date) -lt $deadline) {
    if (Test-MysqlAlive) {
        Write-Output "MySQL started with datadir: $dataDir"
        exit 0
    }
    if ($serverProc.HasExited) {
        throw "MySQL exited early (exit=$($serverProc.ExitCode)). Check $stderrLog"
    }
    Start-Sleep -Seconds 1
}

throw "MySQL did not start within 25 seconds. Check $stderrLog"
