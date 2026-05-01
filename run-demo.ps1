# =============================================================
# Drone Command Center — one-shot demo launcher (Windows / PowerShell)
# -------------------------------------------------------------
# Usage:   .\run-demo.ps1
# What it does:
#   1. Loads .env (creates from .env.example if missing)
#   2. Starts Postgres + backend via docker compose
#   3. Waits for /actuator/health to report UP
#   4. Prints next manual steps (frontend + bridge + AirSim)
# =============================================================

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Drone Command Center — demo launcher" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ---- 1. .env handling ----
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "[setup] .env not found — created from .env.example." -ForegroundColor Yellow
        Write-Host "[setup] Edit .env to set real passwords, then rerun this script." -ForegroundColor Yellow
        exit 1
    } else {
        Write-Error ".env.example is missing. Cannot continue."
        exit 1
    }
}

# Load .env into the current process so docker compose picks it up
Get-Content ".env" | ForEach-Object {
    if ($_ -match '^\s*#') { return }
    if ($_ -match '^\s*$') { return }
    if ($_ -match '^\s*([^=]+?)\s*=\s*(.*)$') {
        $name  = $matches[1].Trim()
        $value = $matches[2].Trim()
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}
Write-Host "[setup] Loaded .env" -ForegroundColor Green

# ---- 2. Docker preflight ----
try {
    docker version --format '{{.Server.Version}}' | Out-Null
} catch {
    Write-Error "Docker Desktop is not running. Start Docker, then rerun this script."
    exit 1
}
Write-Host "[setup] Docker is running" -ForegroundColor Green

# ---- 3. Bring up the stack ----
Write-Host ""
Write-Host "[compose] Building & starting Postgres + backend ..." -ForegroundColor Cyan
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# ---- 4. Wait for backend health ----
$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8080" }
$healthUrl   = "http://localhost:$backendPort/actuator/health"
$timeoutSec  = 120
$elapsed     = 0
$intervalSec = 3

Write-Host ""
Write-Host "[health] Waiting for $healthUrl ..." -ForegroundColor Cyan

while ($elapsed -lt $timeoutSec) {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 3 -ErrorAction Stop
        if ($response.status -eq "UP") {
            Write-Host "[health] Backend is UP" -ForegroundColor Green
            break
        }
    } catch {
        # not ready yet
    }
    Start-Sleep -Seconds $intervalSec
    $elapsed += $intervalSec
    Write-Host "  ... still waiting ($elapsed s)" -ForegroundColor DarkGray
}

if ($elapsed -ge $timeoutSec) {
    Write-Host "[health] Backend did not become healthy within $timeoutSec s." -ForegroundColor Red
    Write-Host "        Check logs:  docker compose logs backend" -ForegroundColor Red
    exit 1
}

# ---- 5. Done ----
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  READY" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Backend:    http://localhost:$backendPort" -ForegroundColor White
Write-Host "  Swagger:    http://localhost:$backendPort/swagger-ui.html" -ForegroundColor White
Write-Host "  Health:     $healthUrl" -ForegroundColor White
Write-Host ""
Write-Host "  Next steps (run in separate terminals):" -ForegroundColor Yellow
Write-Host "    1. Frontend:  cd frontend; flutter run -d windows ``" -ForegroundColor White
Write-Host "                    --dart-define=API_BASE_URL=http://localhost:$backendPort ``" -ForegroundColor White
Write-Host "                    --dart-define=WS_URL=ws://localhost:$backendPort/ws/telemetry" -ForegroundColor White
Write-Host "    2. AirSim:    Launch your AirSim/Unreal scene on the host." -ForegroundColor White
Write-Host "    3. Bridge:    cd capstone\airsim_testing; python airsim_auto_bridge.py" -ForegroundColor White
Write-Host ""
Write-Host "  Stop everything:  docker compose down" -ForegroundColor DarkGray
Write-Host "  Wipe DB volume :  docker compose down -v" -ForegroundColor DarkGray
Write-Host ""
