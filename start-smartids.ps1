param(
    [string]$BaseUrl = "http://127.0.0.1:3000",
    [switch]$HideWindows
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$backendCompose = Join-Path $backendDir "docker-compose.yml"
$venvPython = Join-Path $root ".venv_windows\Scripts\python.exe"

function Get-AvailablePort {
    param(
        [int]$StartPort = 3100,
        [int]$MaxTries = 20
    )

    for ($i = 0; $i -lt $MaxTries; $i++) {
        $port = $StartPort + $i
        $listener = $null
        try {
            $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
            $listener.Start()
            return $port
        } catch {
            continue
        } finally {
            if ($listener) {
                $listener.Stop()
            }
        }
    }

    throw "No available port found from $StartPort to $($StartPort + $MaxTries - 1)."
}

if (-not (Test-Path -LiteralPath $backendDir)) {
    throw "Backend directory not found: $backendDir"
}
if (-not (Test-Path -LiteralPath $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}
if (-not (Test-Path -LiteralPath $backendCompose)) {
    throw "Backend docker-compose file not found: $backendCompose"
}

if (Test-Path -LiteralPath $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = "python"
}

$windowStyle = if ($HideWindows) { "Hidden" } else { "Normal" }

Write-Host "[1/6] Starting local infra (backend/docker-compose.yml)..."
docker compose -f "$backendCompose" up -d

Write-Host "[2/6] Applying backend migrations..."
& $pythonExe ".\backend\script.py" migrate upgrade

$backendPort = Get-AvailablePort -StartPort 3100 -MaxTries 20
$backendBaseUrl = "http://127.0.0.1:$backendPort"

Write-Host "[3/6] Starting backend API in new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$root'; & '$pythonExe' '.\backend\script.py' start --port $backendPort"
) -WindowStyle $windowStyle

Write-Host "[4/6] Starting backend worker in new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$root'; & '$pythonExe' '.\backend\script.py' worker"
) -WindowStyle $windowStyle

Write-Host "[5/6] Starting frontend dev server in new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$frontendDir'; `$env:IDS_REST_BASE_URL='$backendBaseUrl/api/v1'; `$env:NEXT_PUBLIC_IDS_WS_URL='ws://127.0.0.1:$backendPort/api/v1/realtime/ws'; bun run dev -- --port 3000"
) -WindowStyle $windowStyle

Write-Host "[6/6] Starting IDS runtime (packet capture + ML) in new terminal..."
Start-Process powershell -ArgumentList @(
    "-NoExit",
    "-Command",
    "Set-Location -LiteralPath '$root'; `$env:SMARTIDS_IDS_EVENT_ENDPOINT='$backendBaseUrl/api/v1/ids-events'; `$env:SMARTIDS_SESSION_UPDATE_ENDPOINT='$backendBaseUrl/api/v1/sessions/upsert'; `$env:SMARTIDS_BLOCK_EVENT_ENDPOINT='$backendBaseUrl/api/v1/block-events/upsert'; `$env:SMARTIDS_COMMANDS_ENDPOINT='$backendBaseUrl/api/v1/engine-commands'; `$env:SMARTIDS_COMMANDS_ACK_ENDPOINT='$backendBaseUrl/api/v1/engine-commands/ack'; & '$pythonExe' -m packet_capture.main"
) -WindowStyle $windowStyle

$runtimeStatePath = Join-Path $root ".smartids-runtime.env"
Set-Content -LiteralPath $runtimeStatePath -Value @(
    "SMARTIDS_BACKEND_BASE_URL=$backendBaseUrl",
    "SMARTIDS_BACKEND_PORT=$backendPort",
    "IDS_REST_BASE_URL=$backendBaseUrl/api/v1",
    "NEXT_PUBLIC_IDS_WS_URL=ws://127.0.0.1:$backendPort/api/v1/realtime/ws"
)

Write-Host "Started SmartIDS services."
Write-Host "- Backend API:    $backendBaseUrl"
Write-Host "- Frontend:       http://127.0.0.1:3001 (or next available port)"
Write-Host "- IDS runtime:    packet_capture.main"
Write-Host "- Runtime file:   .smartids-runtime.env"
if ($HideWindows) {
    Write-Host "- Process windows are hidden."
}
