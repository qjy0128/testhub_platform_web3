$repoRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $repoRoot ".local\runtime"

[pscustomobject]@{
    RepoRoot = $repoRoot
    RuntimeRoot = $runtimeRoot
    MysqlData = Join-Path $runtimeRoot "mysql-data"
    MysqlLogs = Join-Path $runtimeRoot "mysql-logs"
    ProbeRoot = Join-Path $repoRoot ".local\probes"
    MiscRoot = Join-Path $repoRoot ".local\misc"
}
