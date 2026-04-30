$ErrorActionPreference = "Stop"

$mysqlRoot = "C:\Program Files\MySQL\MySQL Server 8.4"
$mysqlBin = Join-Path $mysqlRoot "bin"
$mysqlAdmin = Join-Path $mysqlBin "mysqladmin.exe"

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

Normalize-ProcessPathEnvironment

if (-not (Test-Path $mysqlAdmin)) {
    throw "mysqladmin.exe not found under $mysqlBin. Install MySQL Server 8.x or adjust scripts/stop_local_mysql.ps1."
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

if (-not (Test-MysqlAlive)) {
    Write-Output "MySQL is not running."
    exit 0
}

& $mysqlAdmin -h 127.0.0.1 -P 3306 -u root shutdown | Out-Null

$deadline = (Get-Date).AddSeconds(20)
while ((Get-Process mysqld -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {
    Start-Sleep -Milliseconds 500
}

if (Get-Process mysqld -ErrorAction SilentlyContinue) {
    throw "MySQL did not stop within 20 seconds."
}

Write-Output "MySQL stopped."
