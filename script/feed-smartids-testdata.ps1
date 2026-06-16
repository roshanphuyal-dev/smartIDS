param(
    [string]$BaseUrl = ""
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$venvPython = Join-Path $root ".venv_windows\Scripts\python.exe"
$runtimeStatePath = Join-Path $root ".smartids-runtime.env"

if (-not $BaseUrl) {
    if (Test-Path -LiteralPath $runtimeStatePath) {
        $line = Get-Content -LiteralPath $runtimeStatePath | Where-Object { $_ -like "SMARTIDS_BACKEND_BASE_URL=*" } | Select-Object -First 1
        if ($line) {
            $BaseUrl = ($line -split "=", 2)[1]
        }
    }
}

if (-not $BaseUrl) {
    $BaseUrl = "http://127.0.0.1:3000"
}

if (Test-Path -LiteralPath $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonExe = "python"
}

Write-Host "Replaying known backend smoke payloads into SmartIDS..."
Write-Host "Target backend: $BaseUrl"

& $pythonExe ".\backend\smoke\api_smoke_unified_reporting.py" --base-url $BaseUrl
& $pythonExe ".\backend\smoke\api_smoke_sessions.py" --base-url $BaseUrl
& $pythonExe ".\backend\smoke\api_smoke_alerts_threats.py" --base-url $BaseUrl
& $pythonExe ".\backend\smoke\api_smoke_blocked_ips.py" --base-url $BaseUrl
& $pythonExe ".\backend\smoke\api_smoke_response_actions.py" --base-url $BaseUrl

Write-Host "PASS: SmartIDS test data replay complete"
