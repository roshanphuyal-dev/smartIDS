$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptRoot = Split-Path -Parent $scriptDir
$root = Split-Path -Parent $scriptRoot
$startScript = Join-Path $root "script\start-smartids.ps1"

if (-not (Test-Path -LiteralPath $startScript)) {
    throw "Missing launcher script: $startScript"
}

$content = Get-Content -LiteralPath $startScript -Raw

$requiredFiles = @(
    "script\runtime\start-smartids-backend-api.ps1",
    "script\runtime\start-smartids-backend-worker.ps1",
    "script\runtime\start-smartids-frontend.ps1",
    "script\runtime\start-smartids-ids-runtime.ps1"
)

foreach ($relativePath in $requiredFiles) {
    $absolutePath = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $absolutePath)) {
        throw "Missing wrapper script: $relativePath"
    }

    $fileName = [System.IO.Path]::GetFileName($relativePath)
    if ($content -notmatch [Regex]::Escape($fileName)) {
        throw "Launcher does not reference wrapper script: $fileName"
    }
}

if ($content -notmatch "function\s+Wait-ForTcpPort") {
    throw "Launcher is missing Wait-ForTcpPort readiness helper."
}

if ($content -match '\[string\]\$Host\b') {
    throw "Launcher readiness helper still declares a Host parameter that collides with PowerShell's built-in `$Host variable."
}

if ($content -notmatch 'Wait-ForTcpPort\s+-Port\s+\$backendPort') {
    throw "Launcher does not wait for backend readiness."
}

if ($content -notmatch 'Wait-ForTcpPort\s+-Port\s+3000') {
    throw "Launcher does not wait for frontend readiness."
}

Write-Host "PASS: SmartIDS launcher structure smoke"
