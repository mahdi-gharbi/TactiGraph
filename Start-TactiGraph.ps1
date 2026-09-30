param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$url = 'http://127.0.0.1:8003'
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logRoot = Join-Path $projectRoot 'output'

function Test-TactiGraph {
    try {
        $health = Invoke-RestMethod -Uri "$url/api/v1/health" -TimeoutSec 3
        return ($health.status -eq 'ok' -and $health.mode -eq 'local')
    } catch { return $false }
}

if (-not (Test-TactiGraph)) {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw 'Python environment missing. Follow the Quick start in README.md first.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\dist\index.html'))) {
        throw 'Frontend build missing. Run npm.cmd --prefix frontend run build first.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'data\tactigraph.db'))) {
        throw 'Research database missing. Follow the ingestion instructions in README.md.'
    }
    New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
    # Explicit local mode, without changing saved settings or exposing secret values.
    $oldMode = $env:TACTIGRAPH_MODE
    $oldDatabase = $env:TACTIGRAPH_DATABASE_URL
    try {
        $env:TACTIGRAPH_MODE = 'local'
        $env:TACTIGRAPH_DATABASE_URL = 'sqlite:///data/tactigraph.db'
        $process = Start-Process -FilePath $pythonPath -ArgumentList @('-u','-m','tactigraph.cli','serve','--host','127.0.0.1','--port','8003') -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'local-server.stdout.log') -RedirectStandardError (Join-Path $logRoot 'local-server.stderr.log') -PassThru
    } finally {
        $env:TACTIGRAPH_MODE = $oldMode
        $env:TACTIGRAPH_DATABASE_URL = $oldDatabase
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-TactiGraph) { $ready = $true; break }
        $process.Refresh()
        if ($process.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "Server could not start. See output\local-server.stderr.log; port 8003 may already be used by another app." }
}
Write-Host "TactiGraph is running at $url"
Write-Host "User guide: $url/guide"
if (-not $NoBrowser) { Start-Process $url }
