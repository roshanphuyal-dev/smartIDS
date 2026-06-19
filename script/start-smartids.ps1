param(
    [string]$BaseUrl = "http://127.0.0.1:3100",
    [switch]$HideWindows
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]::new($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Wait-ForTcpPort {
    param(
        [string]$TargetHost = "127.0.0.1",
        [int]$Port,
        [int]$TimeoutSeconds = 45,
        [System.Diagnostics.Process]$WatchProcess,
        [string]$Label
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ($WatchProcess) {
            $WatchProcess.Refresh()
            if ($WatchProcess.HasExited) {
                throw "$Label exited before port $Port became ready."
            }
        }

        $client = $null
        try {
            $client = [System.Net.Sockets.TcpClient]::new()
            $connectTask = $client.ConnectAsync($TargetHost, $Port)
            if ($connectTask.Wait(1000) -and $client.Connected) {
                $client.Close()
                return
            }
        } catch {
        } finally {
            if ($client) {
                $client.Dispose()
            }
        }

        Start-Sleep -Milliseconds 500
    }

    throw "Timed out waiting for $Label on $TargetHost`:$Port."
}

function Start-SmartIDSProcess {
    param(
        [string]$Label,
        [string]$ScriptPath,
        [string[]]$ScriptArguments,
        [string]$WindowStyle
    )

    $startArgs = @(
        "-NoExit",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $ScriptPath
    ) + $ScriptArguments

    return Start-Process powershell -ArgumentList $startArgs -WindowStyle $WindowStyle -PassThru
}

if (-not (Test-IsAdministrator)) {
    throw "SmartIDS start requires an Administrator PowerShell session on Windows."
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$backendCompose = Join-Path $backendDir "docker-compose.yml"
$venvPython = Join-Path $root ".venv_windows\Scripts\python.exe"
$runtimeScriptsDir = Join-Path $scriptDir "runtime"
$backendApiScript = Join-Path $runtimeScriptsDir "start-smartids-backend-api.ps1"
$backendWorkerScript = Join-Path $runtimeScriptsDir "start-smartids-backend-worker.ps1"
$frontendScript = Join-Path $runtimeScriptsDir "start-smartids-frontend.ps1"
$idsRuntimeScript = Join-Path $runtimeScriptsDir "start-smartids-ids-runtime.ps1"

foreach ($path in @($backendDir, $frontendDir, $backendCompose, $backendApiScript, $backendWorkerScript, $frontendScript, $idsRuntimeScript)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required path not found: $path"
    }
}

if (Test-Path -LiteralPath $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = "python"
}

$windowStyle = if ($HideWindows) { "Hidden" } else { "Normal" }
$backendBaseUrl = $BaseUrl.TrimEnd("/")
$backendUri = [System.Uri]$backendBaseUrl
$backendPort = $backendUri.Port

Write-Host "[1/8] Starting local infra (backend/docker-compose.yml)..."
docker compose -f "$backendCompose" up -d

Write-Host "[2/8] Applying backend migrations..."
& $pythonExe ".\backend\script.py" migrate upgrade

Write-Host "[3/8] Starting backend API in dedicated terminal..."
$backendApiProcess = Start-SmartIDSProcess `
    -Label "backend API" `
    -ScriptPath $backendApiScript `
    -ScriptArguments @("-Root", $root, "-PythonExe", $pythonExe, "-Port", "$backendPort") `
    -WindowStyle $windowStyle

Write-Host "[4/8] Waiting for backend API readiness on port $backendPort..."
Wait-ForTcpPort -Port $backendPort -TimeoutSeconds 60 -WatchProcess $backendApiProcess -Label "backend API"

Write-Host "[5/8] Starting backend worker in dedicated terminal..."
$backendWorkerProcess = Start-SmartIDSProcess `
    -Label "backend worker" `
    -ScriptPath $backendWorkerScript `
    -ScriptArguments @("-Root", $root, "-PythonExe", $pythonExe) `
    -WindowStyle $windowStyle

Write-Host "[6/8] Starting frontend dev server in dedicated terminal..."
$frontendProcess = Start-SmartIDSProcess `
    -Label "frontend dev" `
    -ScriptPath $frontendScript `
    -ScriptArguments @("-FrontendDir", $frontendDir, "-BackendBaseUrl", $backendBaseUrl, "-BackendPort", "$backendPort") `
    -WindowStyle $windowStyle

Write-Host "[7/8] Waiting for frontend readiness on port 3000..."
Wait-ForTcpPort -Port 3000 -TimeoutSeconds 60 -WatchProcess $frontendProcess -Label "frontend dev server"

Write-Host "[8/8] Starting IDS runtime in dedicated terminal..."
$idsRuntimeProcess = Start-SmartIDSProcess `
    -Label "IDS runtime" `
    -ScriptPath $idsRuntimeScript `
    -ScriptArguments @("-Root", $root, "-PythonExe", $pythonExe, "-BackendBaseUrl", $backendBaseUrl) `
    -WindowStyle $windowStyle

$runtimeStatePath = Join-Path $root ".smartids-runtime.env"
Set-Content -LiteralPath $runtimeStatePath -Value @(
    "SMARTIDS_BACKEND_BASE_URL=$backendBaseUrl",
    "SMARTIDS_BACKEND_PORT=$backendPort",
    "NEXT_PUBLIC_IDS_REST_BASE_URL=$backendBaseUrl/api/v1",
    "IDS_REST_BASE_URL=$backendBaseUrl/api/v1",
    "NEXT_PUBLIC_IDS_WS_URL=ws://127.0.0.1:$backendPort/api/v1/realtime/ws"
)

Write-Host "Started SmartIDS services."
Write-Host "- Backend API:    $backendBaseUrl"
Write-Host "- Frontend:       http://127.0.0.1:3000"
Write-Host "- IDS runtime:    packet_capture.main"
Write-Host "- Runtime file:   .smartids-runtime.env"
if ($HideWindows) {
    Write-Host "- Process windows are hidden."
}
