param(
    [switch]$StopDocker
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendCompose = Join-Path $root "backend\docker-compose.yml"

function Stop-ByCommandPattern {
    param(
        [string]$Pattern,
        [string]$Label
    )

    $procs = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -and $_.CommandLine -match $Pattern
    }

    if (-not $procs) {
        Write-Host "No process found for $Label"
        return
    }

    foreach ($proc in $procs) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
            Write-Host "Stopped $Label (PID $($proc.ProcessId))"
        } catch {
            Write-Host "Failed to stop $Label (PID $($proc.ProcessId)): $($_.Exception.Message)"
        }
    }
}

Write-Host "Stopping SmartIDS processes..."

Stop-ByCommandPattern -Pattern "backend\\script\.py\s+start" -Label "backend API"
Stop-ByCommandPattern -Pattern "-m\s+uvicorn\s+app\.main:app" -Label "backend API (uvicorn)"
Stop-ByCommandPattern -Pattern "-m\s+celery\s+-A\s+app\.worker\.celery_app:celery_app\s+worker" -Label "backend worker"
Stop-ByCommandPattern -Pattern "bun\s+--bun\s+next\s+dev" -Label "frontend dev server"
Stop-ByCommandPattern -Pattern "-m\s+packet_capture\.main" -Label "IDS runtime"

if ($StopDocker) {
    if (Test-Path -LiteralPath $backendCompose) {
        Write-Host "Stopping backend docker services..."
        docker compose -f "$backendCompose" down
    } else {
        Write-Host "Skipped docker stop: compose file missing at $backendCompose"
    }
}

Write-Host "SmartIDS stop sequence complete."
