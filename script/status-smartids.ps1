$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
$runtimeStatePath = Join-Path $root ".smartids-runtime.env"

function Find-ByCommandPattern {
    param([string]$Pattern)
    return Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match $Pattern
    }
}

function Show-ProcessStatus {
    param(
        [string]$Label,
        [string]$Pattern
    )

    $matches = Find-ByCommandPattern -Pattern $Pattern
    if (-not $matches) {
        Write-Host ("{0,-24}: stopped" -f $Label)
        return
    }

    $pids = ($matches | ForEach-Object { $_.ProcessId }) -join ","
    Write-Host ("{0,-24}: running (pid {1})" -f $Label, $pids)
}

Write-Host "SmartIDS status"
Write-Host "==============="

if (Test-Path -LiteralPath $runtimeStatePath) {
    Write-Host "Runtime env: $runtimeStatePath"
    Get-Content -LiteralPath $runtimeStatePath | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "Runtime env: not found (.smartids-runtime.env)"
}

Write-Host ""
Write-Host "Process status"
Write-Host "--------------"
Show-ProcessStatus -Label "backend API" -Pattern "-m\s+uvicorn\s+app\.main:app"
Show-ProcessStatus -Label "backend worker" -Pattern "-m\s+celery\s+-A\s+app\.worker\.celery_app:celery_app\s+worker"
Show-ProcessStatus -Label "frontend dev" -Pattern "bun\s+--bun\s+next\s+dev"
Show-ProcessStatus -Label "IDS runtime" -Pattern "-m\s+packet_capture\.main"

Write-Host ""
Write-Host "Port status"
Write-Host "-----------"
foreach ($port in @(3000, 3001, 3100, 6379, 8080)) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        Write-Host ("port {0,-5}: listening" -f $port)
    } else {
        Write-Host ("port {0,-5}: closed" -f $port)
    }
}
