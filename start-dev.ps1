#Requires -Version 5.1
# Start FastAPI + Vite; waits for Postgres on 5432. Use -UseDocker to start Postgres via Docker Compose.
param([switch]$UseDocker)

$ErrorActionPreference = "Stop"
$Root = if ($PSScriptRoot) { $PSScriptRoot } else { Get-Location }
Set-Location $Root

function Test-TcpOpen {
    param([string]$ComputerName = "127.0.0.1", [int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.ReceiveTimeout = 2
        $client.SendTimeout = 2
        $client.Connect($ComputerName, $Port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Wait-Port {
    param([int]$Port, [int]$TimeoutSec = 120)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-TcpOpen -Port $Port) {
            return
        }
        Start-Sleep -Seconds 1
    }
    throw "Timed out after ${TimeoutSec}s waiting for port $Port (PostgreSQL)."
}

function Escape-SingleQuoted([string]$s) {
    return $s.Replace("'", "''")
}

function Encode-PwshCommand([string]$Script) {
    $bytes = [System.Text.Encoding]::Unicode.GetBytes($Script)
    return [Convert]::ToBase64String($bytes)
}

Write-Host ""
Write-Host "=== FIR Automation - dev stack ===" -ForegroundColor Cyan
Write-Host "Root: $Root"
Write-Host ""

# PostgreSQL: local service by default; -UseDocker uses compose
$dbUp = Test-TcpOpen -Port 5432
if ($UseDocker.IsPresent -and $dbUp) {
    Write-Host "[DB] Port 5432 already open - using existing PostgreSQL." -ForegroundColor Yellow
} elseif ($UseDocker.IsPresent) {
    Write-Host "[DB] -UseDocker: starting postgres via Docker Compose..." -ForegroundColor Cyan
    $composeFile = Join-Path $Root "docker-compose.yml"
    docker compose -f $composeFile up -d postgres
    if ($LASTEXITCODE -ne 0) {
        Write-Error "docker compose failed (exit $LASTEXITCODE)."
    }
    Write-Host "[DB] Waiting for PostgreSQL on 5432..." -ForegroundColor Cyan
    Wait-Port -Port 5432
    Write-Host "[DB] Ready." -ForegroundColor Green
} elseif ($dbUp) {
    Write-Host "[DB] PostgreSQL reachable on 127.0.0.1:5432" -ForegroundColor Green
} else {
    Write-Host "[DB] Waiting for PostgreSQL on 127.0.0.1:5432 ..." -ForegroundColor Yellow
    Write-Host "     Start the service: Win+R -> services.msc -> PostgreSQL -> Start" -ForegroundColor DarkGray
    Write-Host "     Or: start-dev.bat -UseDocker (Docker Postgres)" -ForegroundColor DarkGray
    Wait-Port -Port 5432
    Write-Host "[DB] PostgreSQL is up." -ForegroundColor Green
}

$py = Join-Path $Root "saas\backend\venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host ""
    Write-Host "Missing: $py" -ForegroundColor Red
    Write-Host "Create the venv once:" -ForegroundColor Yellow
    Write-Host "  cd saas\backend" -ForegroundColor Gray
    Write-Host "  python -m venv venv" -ForegroundColor Gray
    Write-Host "  .\venv\Scripts\activate" -ForegroundColor Gray
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Gray
    exit 1
}

$fe = Join-Path $Root "saas\frontend"
if (-not (Test-Path (Join-Path $fe "node_modules"))) {
    Write-Host "[UI] Installing frontend dependencies (npm install)..." -ForegroundColor Cyan
    Push-Location $fe
    npm install
    Pop-Location
}

# Use child PowerShell with -EncodedCommand (avoids cmd quoting: unquoted `&&` made npm run from repo root).
$be = Join-Path $Root "saas\backend"
$apiScript = "Set-Location -LiteralPath '$(Escape-SingleQuoted $be)'; & '$(Escape-SingleQuoted $py)' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
$uiScript = "Set-Location -LiteralPath '$(Escape-SingleQuoted $fe)'; npm run dev"
$apiArg = "powershell.exe -NoProfile -NonInteractive -EncodedCommand $(Encode-PwshCommand $apiScript)"
$uiArg = "powershell.exe -NoProfile -NonInteractive -EncodedCommand $(Encode-PwshCommand $uiScript)"

Write-Host ""
Write-Host "API  -> http://127.0.0.1:8000/health" -ForegroundColor Green
Write-Host "App  -> http://127.0.0.1:5173" -ForegroundColor Green
Write-Host "Stop -> Ctrl+C (stops API + UI only)" -ForegroundColor DarkGray
Write-Host ""

& npx --yes concurrently@9 `
    -k `
    -n "API,WEB" `
    -c "green,cyan" `
    $apiArg `
    $uiArg
